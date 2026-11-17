"""Build the published index.json from specs/.

Usage: python scripts/build_index.py <output_dir>
Writes <output_dir>/index.json and copies the schema to <output_dir>/schema/.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from common import PROFILE_SCHEMA_PATH, SCHEMA_PATH, check_profile, check_spec, load_all_profiles, load_all_specs

INDEX_FORMAT = 1


def build() -> dict:
    specs = []
    for path, spec in load_all_specs():
        errors = check_spec(spec, path)
        if errors:
            raise SystemExit(f"{path}: refusing to publish invalid spec: {errors}")
        specs.append(spec)
    profiles = []
    for path, profile in load_all_profiles():
        errors = check_profile(profile, path)
        if errors:
            raise SystemExit(f"{path}: refusing to publish invalid profile: {errors}")
        profiles.append(profile)
    profiles.sort(key=lambda p: p["name"].lower())
    specs.sort(key=lambda s: (s["brand"].lower(), s["model"].lower(), s.get("variant", ""), s["id"]))
    return {
        "index_format": INDEX_FORMAT,
        "schema_version": 1,
        "generated": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "count": len(specs),
        "brands": sorted({s["brand"] for s in specs}, key=str.lower),
        "regions": sorted({r for s in specs for r in s["regions"]}),
        "specs": specs,
        "profiles": profiles,
    }


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "_site")
    out.mkdir(parents=True, exist_ok=True)
    index = build()
    (out / "index.json").write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    (out / "schema").mkdir(exist_ok=True)
    for schema in (SCHEMA_PATH, PROFILE_SCHEMA_PATH):
        shutil.copy(schema, out / "schema" / schema.name)
    print(f"Wrote {out / 'index.json'} with {index['count']} spec(s) and {len(index['profiles'])} profile(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
