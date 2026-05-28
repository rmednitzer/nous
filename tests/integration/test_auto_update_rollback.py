"""Auto-update must never leave HEAD advanced past a failed deploy.

Regression guard for the dormant-freeze mode: ``deploy/auto-update.sh``
used to ``git reset --hard origin/main`` before running ``install.sh``,
so a failed install left HEAD at the new commit while the service still
ran the old code. The next tick then saw ``LOCAL == REMOTE`` and exited
as a no-op, freezing the box on the stale build with no marker.

The two cases below also pin the rollback semantics raised in PR review:

* a transient install failure (before the new build is bounced into
  service) rolls HEAD back but must NOT blacklist the commit, or the
  skip guard would refuse a good commit forever;
* a post-restart health-check failure (the new build is proven bad)
  rolls HEAD back AND records the commit in ``last_failed``.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_UPDATE = REPO_ROOT / "deploy" / "auto-update.sh"

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}

# Stub systemctl that succeeds for every subcommand.
_SYSTEMCTL_OK = "#!/usr/bin/env bash\nexit 0\n"
# Stub systemctl whose `is-active` health check fails (the deployed build
# came up but is unhealthy) while every other subcommand succeeds.
_SYSTEMCTL_UNHEALTHY = (
    "#!/usr/bin/env bash\n"
    'for a in "$@"; do [ "$a" = "is-active" ] && exit 1; done\n'
    "exit 0\n"
)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **_GIT_ENV},
    )
    return out.stdout.strip()


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _init_repo(tmp_path: Path, install_body: str) -> tuple[Path, str, str]:
    """Build a bare origin + working clone with two commits.

    ``install_body`` is the contents of ``deploy/install.sh`` shared by
    both commits. Returns (repo, local_sha, remote_sha) with the working
    tree checked out on the older (local) commit and origin/main on the
    newer (remote) commit, so auto-update.sh sees an update to apply.
    """
    origin = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-b", "main", str(origin)],
        check=True,
        capture_output=True,
    )
    repo = tmp_path / "repo"
    subprocess.run(
        ["git", "clone", str(origin), str(repo)], check=True, capture_output=True
    )

    install = repo / "deploy" / "install.sh"
    install.parent.mkdir()
    install.write_text(install_body)
    _make_executable(install)

    (repo / "marker").write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v1 good")
    local_sha = _git(repo, "rev-parse", "HEAD")

    (repo / "marker").write_text("v2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v2 candidate")
    remote_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "--quiet", "origin", "main")

    # Put the working tree back on the old good commit so auto-update sees
    # LOCAL != REMOTE and attempts the deploy.
    _git(repo, "reset", "--hard", local_sha)
    assert _git(repo, "rev-parse", "HEAD") == local_sha
    return repo, local_sha, remote_sha


def _run_auto_update(
    tmp_path: Path, repo: Path, systemctl_body: str
) -> tuple[subprocess.CompletedProcess[str], Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    systemctl = bindir / "systemctl"
    systemctl.write_text(systemctl_body)
    _make_executable(systemctl)

    logdir = tmp_path / "log"
    logdir.mkdir()

    result = subprocess.run(
        ["bash", str(AUTO_UPDATE)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
            "REPO_DIR": str(repo),
            "LOG_DIR": str(logdir),
        },
    )
    return result, logdir


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_failed_install_rolls_back_without_blacklisting(tmp_path: Path) -> None:
    repo, local_sha, _ = _init_repo(tmp_path, "#!/usr/bin/env bash\nexit 1\n")
    result, logdir = _run_auto_update(tmp_path, repo, _SYSTEMCTL_OK)

    diagnostics = result.stdout + result.stderr
    assert result.returncode != 0, diagnostics
    # HEAD is rolled back, so the next tick sees LOCAL != REMOTE rather
    # than mistaking the box for up-to-date.
    assert _git(repo, "rev-parse", "HEAD") == local_sha, diagnostics
    # A transient install failure must not permanently trip the skip guard.
    last_failed = logdir / "auto-update.last_failed"
    assert not last_failed.exists(), last_failed.read_text()


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_failed_health_check_rolls_back_and_blacklists(tmp_path: Path) -> None:
    repo, local_sha, remote_sha = _init_repo(tmp_path, "#!/usr/bin/env bash\nexit 0\n")
    result, logdir = _run_auto_update(tmp_path, repo, _SYSTEMCTL_UNHEALTHY)

    diagnostics = result.stdout + result.stderr
    assert result.returncode != 0, diagnostics
    assert _git(repo, "rev-parse", "HEAD") == local_sha, diagnostics
    # A build that was bounced into service and failed its health check is
    # proven bad, so the skip guard records it.
    last_failed = logdir / "auto-update.last_failed"
    assert last_failed.exists() and remote_sha in last_failed.read_text(), diagnostics
