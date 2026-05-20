"""Entry point so ``python -m nous`` works the same as the ``nous`` script."""

from __future__ import annotations

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
