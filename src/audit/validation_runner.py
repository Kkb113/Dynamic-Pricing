from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .report_builder import run as run_audit

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT, check=False)
    if tests.returncode != 0:
        raise SystemExit(tests.returncode)
    raise SystemExit(run_audit())


if __name__ == "__main__":
    main()
