"""Auto-update must never leave HEAD advanced past a failed deploy.

Regression guard for the dormant-freeze mode: ``deploy/auto-update.sh``
used to ``git reset --hard origin/main`` before running ``install.sh``,
so a failed install left HEAD at the new commit while the service still
ran the old code. The next tick then saw ``LOCAL == REMOTE`` and exited
as a no-op, freezing the box on the stale build with no marker. The fix
wraps the critical section in an EXIT trap that rolls HEAD back and
records the broken commit in ``last_failed``.
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


@pytest.mark.skipif(shutil.which("git") is None, reason="git is required")
def test_failed_install_rolls_head_back(tmp_path: Path) -> None:
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

    deploy = repo / "deploy"
    deploy.mkdir()
    # An install.sh that always fails stands in for a broken dependency set.
    install = deploy / "install.sh"
    install.write_text("#!/usr/bin/env bash\nexit 1\n")
    _make_executable(install)

    (repo / "marker").write_text("v1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v1 good")
    local_sha = _git(repo, "rev-parse", "HEAD")

    # Advance origin/main to the "broken" deploy target.
    (repo / "marker").write_text("v2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "v2 broken install")
    remote_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "push", "--quiet", "origin", "main")

    # Put the working tree back on the old good commit so auto-update sees
    # LOCAL != REMOTE and attempts the (failing) deploy.
    _git(repo, "reset", "--hard", local_sha)
    assert _git(repo, "rev-parse", "HEAD") == local_sha

    # Stub systemctl so the script's daemon-reload / restart / status calls
    # no-op without touching the host.
    bindir = tmp_path / "bin"
    bindir.mkdir()
    systemctl = bindir / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n")
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

    diagnostics = result.stdout + result.stderr
    assert result.returncode != 0, diagnostics
    # The working tree is rolled back to the previous good commit, so the
    # next tick sees LOCAL != REMOTE and does not mistake the box for
    # up-to-date.
    assert _git(repo, "rev-parse", "HEAD") == local_sha, diagnostics
    # The broken commit is recorded so the skip guard engages next tick.
    last_failed = (logdir / "auto-update.last_failed").read_text()
    assert remote_sha in last_failed, last_failed
