"""Create or verify the sanitized Phase 0 transfer manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dynamic_pricing.release import build_release_manifest, verify_release_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        report = verify_release_manifest(args.root, json.loads(args.verify.read_text(encoding="utf-8")))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["status"] == "PASS" else 2
    manifest = build_release_manifest(args.root, require_clean=not args.allow_dirty)
    if args.output:
        manifest.write(args.output)
    print(json.dumps({key: value for key, value in manifest.payload.items() if key != "files"}, indent=2, sort_keys=True))
    return 0 if manifest.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
