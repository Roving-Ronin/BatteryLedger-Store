"""Validate every spec in specs/. Exits non-zero on any error."""

from __future__ import annotations

import json
import sys

from common import ROOT, check_profile, check_spec, find_conflicts, iter_profile_files, iter_spec_files


def main() -> int:
    loaded = []
    failed = False
    for path in iter_spec_files():
        rel = path.relative_to(ROOT)
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            print(f"::error file={rel}::invalid JSON: {err}")
            failed = True
            continue
        errors = check_spec(spec, path)
        for e in errors:
            print(f"::error file={rel}::{e}")
        failed |= bool(errors)
        if not errors:
            loaded.append((path, spec))

    seen_ids = {}
    for path, spec in loaded:
        if spec["id"] in seen_ids:
            print(f"::error file={path.relative_to(ROOT)}::duplicate id also in {seen_ids[spec['id']]}")
            failed = True
        seen_ids[spec["id"]] = path.relative_to(ROOT)
        for c in find_conflicts(spec, loaded):
            print(f"::error file={path.relative_to(ROOT)}::{c}")
            failed = True

    profiles = 0
    for path in iter_profile_files():
        rel = path.relative_to(ROOT)
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            print(f"::error file={rel}::invalid JSON: {err}")
            failed = True
            continue
        for e in check_profile(profile, path):
            print(f"::error file={rel}::{e}")
            failed = True
        profiles += 1

    print(f"{len(loaded)} spec(s) and {profiles} sensor profile(s) checked, {'FAILED' if failed else 'all valid'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
