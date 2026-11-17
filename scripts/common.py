"""Shared helpers for the BatteryLedger Store scripts.

Run scripts with the repo root as the working directory.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = ROOT / "specs"
SCHEMA_PATH = ROOT / "schema" / "battery-spec.schema.json"
PROFILES_DIR = ROOT / "profiles"
PROFILE_SCHEMA_PATH = ROOT / "schema" / "sensor-profile.schema.json"
PLACEHOLDER_RE = re.compile(r"\{(entry|device|prefix|plant|inverter|station|serial)\}")


def slugify(text: str) -> str:
    """Lowercase, replace anything that isn't a-z/0-9 with single hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def region_group(regions: list[str]) -> str:
    """Suffix used in spec IDs for a set of region codes."""
    codes = sorted(set(regions))
    if codes == ["GLOBAL"]:
        return "global"
    if codes == ["AU", "NZ"]:
        return "anz"
    if len(codes) <= 3:
        return "-".join(c.lower() for c in codes)
    return "multi"


def make_spec_id(brand: str, model: str, variant: str | None, regions: list[str]) -> str:
    parts = [slugify(brand), slugify(model)]
    if variant:
        parts.append(slugify(variant))
    parts.append(region_group(regions))
    return "-".join(p for p in parts if p)


def spec_path(spec: dict) -> Path:
    return SPECS_DIR / slugify(spec["brand"]) / f"{spec['id']}.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validator() -> Draft202012Validator:
    return Draft202012Validator(load_schema(), format_checker=FormatChecker())


def profile_validator() -> Draft202012Validator:
    schema = json.loads(PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def iter_profile_files():
    yield from sorted(PROFILES_DIR.glob("*.json"))


def load_all_profiles() -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in iter_profile_files()]


def check_profile(profile: dict, path: Path | None = None) -> list[str]:
    errors = [
        f"{'/'.join(str(x) for x in e.absolute_path) or '(root)'}: {e.message}"
        for e in sorted(profile_validator().iter_errors(profile), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors
    if path is not None and path.stem != profile["id"]:
        errors.append(f"file name '{path.name}' must be '{profile['id']}.json'")
    for role, rules in profile["roles"].items():
        for i, rule in enumerate(rules):
            names = PLACEHOLDER_RE.findall(rule["unique_id"])
            if len(names) != len(set(names)):
                errors.append(f"roles/{role}/{i}: each placeholder may appear only once")
    return errors


def iter_spec_files():
    yield from sorted(SPECS_DIR.glob("*/*.json"))


def load_all_specs() -> list[tuple[Path, dict]]:
    return [(p, json.loads(p.read_text(encoding="utf-8"))) for p in iter_spec_files()]


def check_spec(spec: dict, path: Path | None = None) -> list[str]:
    """Schema validation plus rules JSON Schema can't express. Returns error strings."""
    errors = [
        f"{'/'.join(str(x) for x in e.absolute_path) or '(root)'}: {e.message}"
        for e in sorted(validator().iter_errors(spec), key=lambda e: list(e.absolute_path))
    ]
    if errors:
        return errors

    if path is not None:
        if path.stem != spec["id"]:
            errors.append(f"file name '{path.name}' must be '{spec['id']}.json'")
        if path.parent.name != slugify(spec["brand"]):
            errors.append(f"spec must live in specs/{slugify(spec['brand'])}/")
    if not spec["id"].startswith(slugify(spec["brand"]) + "-"):
        errors.append(f"id must start with '{slugify(spec['brand'])}-'")

    cap = spec["capacity"]
    if "nominal_kwh" in cap and cap["usable_kwh"] > cap["nominal_kwh"]:
        errors.append("capacity.usable_kwh cannot exceed capacity.nominal_kwh")
    if "min_units" in cap and "max_units" in cap and cap["min_units"] > cap["max_units"]:
        errors.append("capacity.min_units cannot exceed capacity.max_units")
    if cap["unit"] == "system" and cap.get("max_units", 1) != 1:
        errors.append("an all-in-one system spec must not set max_units above 1")

    tp = spec["warranty"]["throughput"]
    if tp["scope"] == "table":
        units = [row["units"] for row in tp["table"]]
        if units != sorted(set(units)):
            errors.append("warranty.throughput.table rows must have unique units in ascending order")
    return errors


def find_conflicts(spec: dict, existing: list[tuple[Path, dict]]) -> list[str]:
    """Other specs with the same brand/model/variant and overlapping regions."""
    key = (slugify(spec["brand"]), slugify(spec["model"]), slugify(spec.get("variant", "")))
    regions = set(spec["regions"])
    out = []
    for path, other in existing:
        if other["id"] == spec["id"]:
            continue
        okey = (slugify(other["brand"]), slugify(other["model"]), slugify(other.get("variant", "")))
        if okey == key and (regions & set(other["regions"]) or "GLOBAL" in regions | set(other["regions"])):
            out.append(f"overlaps existing spec '{other['id']}' ({path.relative_to(ROOT)})")
    return out
