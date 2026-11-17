"""Turn a spec-submission issue into a spec file.

Reads the issue from environment variables (never from the command line, the body is
untrusted input): ISSUE_BODY, ISSUE_AUTHOR. Writes the spec file when valid and always
writes a result JSON to the path given as the first argument:

  {"ok": bool, "errors": [...], "action": "new"|"correction", "spec_id": str,
   "path": str, "title": str, "summary": str}

Two body formats are accepted:
  1. The GitHub issue form (.github/ISSUE_TEMPLATE/spec-submission.yml).
  2. A body from the BatteryLedger integration containing
     <!-- batteryledger-spec --> followed by a ```json fenced block.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date
from pathlib import Path

from common import ROOT, check_spec, find_conflicts, load_all_specs, make_spec_id, spec_path

MARKER = "<!-- batteryledger-spec -->"
NO_RESPONSE = "_No response_"

# Issue form labels (must match spec-submission.yml)
L_SPEC_ID = "Existing spec ID (corrections only)"
L_BRAND = "Brand"
L_SERIES = "Model"
L_MODEL = "Battery module"
L_VARIANT = "Variant"
L_REGIONS = "Regions"
L_CHEM = "Chemistry"
L_PHASES = "Supported phases"
L_UNIT = "Product type"
L_NOMINAL = "Nominal capacity per unit (kWh)"
L_USABLE = "Usable capacity per unit (kWh)"
L_REPORTED = "Capacity reported by the inverter per unit (kWh)"
L_MIN = "Minimum units per system"
L_MAX = "Maximum units per system"
L_YEARS = "Warranty period (years)"
L_EOL = "Warranted end-of-life capacity (%)"
L_BASIS = "Throughput counted as"
L_SCOPE = "Throughput limit applies"
L_TP_KWH = "Throughput limit (kWh)"
L_TP_TABLE = "Throughput table"
L_WNOTES = "Warranty notes"
L_SOURCES = "Sources"
L_NOTES = "Other notes"

BASIS = {
    "Not stated in warranty": "unspecified",
    "Charged energy": "charged",
    "Discharged energy": "discharged",
}
SCOPE = {
    "Per unit": "per_unit",
    "Per system (regardless of unit count)": "per_system",
    "Table by unit count": "table",
    "No throughput limit": "none",
}
UNIT = {"Stackable module": "module", "All-in-one system": "system"}

# Keys a submitter may provide in the JSON route; the rest are set here.
SUBMITTABLE = {"brand", "series", "model", "variant", "regions", "chemistry", "phases",
               "capacity", "warranty", "sources", "notes"}


class SubmissionError(Exception):
    pass


def parse_form_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    parts = re.split(r"^### +(.+?)\s*$", body, flags=re.MULTILINE)
    # parts = [preamble, label1, content1, label2, content2, ...]
    for label, content in zip(parts[1::2], parts[2::2]):
        value = content.strip()
        sections[label.strip()] = "" if value == NO_RESPONSE else value
    return sections


def _num(sections, label, kind=float, required=False):
    raw = sections.get(label, "").replace(",", "").strip()
    if not raw:
        if required:
            raise SubmissionError(f"'{label}' is required")
        return None
    try:
        return kind(raw)
    except ValueError:
        raise SubmissionError(f"'{label}' must be a number, got '{raw}'") from None


def _checked(text: str) -> list[str]:
    return [m.strip() for m in re.findall(r"^- \[[xX]\] (.+)$", text, flags=re.MULTILINE)]


def spec_from_form(sections: dict[str, str]) -> tuple[dict, str | None]:
    def req(label):
        v = sections.get(label, "").strip()
        if not v:
            raise SubmissionError(f"'{label}' is required")
        return v

    spec: dict = {
        "brand": req(L_BRAND),
        "model": req(L_MODEL),
        "regions": [r.strip().upper() for r in re.split(r"[,\s]+", req(L_REGIONS)) if r.strip()],
        "chemistry": req(L_CHEM),
    }
    if sections.get(L_SERIES):
        spec["series"] = sections[L_SERIES].strip()
    if sections.get(L_VARIANT):
        spec["variant"] = sections[L_VARIANT].strip()

    checked = _checked(sections.get(L_PHASES, ""))
    spec["phases"] = [p for p, lbl in (("1", "Single phase"), ("3", "Three phase")) if lbl in checked]
    if not spec["phases"]:
        raise SubmissionError("tick at least one of 'Single phase' / 'Three phase'")

    unit = UNIT.get(req(L_UNIT))
    if unit is None:
        raise SubmissionError(f"unknown '{L_UNIT}'")
    cap = {"unit": unit, "usable_kwh": _num(sections, L_USABLE, required=True)}
    for key, label, kind in (("nominal_kwh", L_NOMINAL, float), ("reported_kwh", L_REPORTED, float),
                             ("min_units", L_MIN, int), ("max_units", L_MAX, int)):
        v = _num(sections, label, kind)
        if v is not None:
            cap[key] = v
    spec["capacity"] = cap

    basis = BASIS.get(req(L_BASIS))
    scope = SCOPE.get(req(L_SCOPE))
    if basis is None or scope is None:
        raise SubmissionError("unknown throughput option")
    tp: dict = {"basis": basis, "scope": scope}
    if scope in ("per_unit", "per_system"):
        tp["kwh"] = _num(sections, L_TP_KWH, required=True)
    elif scope == "table":
        rows = []
        for line in sections.get(L_TP_TABLE, "").splitlines():
            line = line.strip().strip("`")
            if not line:
                continue
            m = re.fullmatch(r"(\d+)\s*=\s*([\d.,]+)", line)
            if not m:
                raise SubmissionError(f"throughput table line '{line}' must look like 3=60000")
            rows.append({"units": int(m.group(1)), "kwh": float(m.group(2).replace(",", ""))})
        if not rows:
            raise SubmissionError("'Throughput table' is required for 'Table by unit count'")
        tp["table"] = rows
    spec["warranty"] = {
        "years": _num(sections, L_YEARS, required=True),
        "eol_capacity_pct": _num(sections, L_EOL, required=True),
        "throughput": tp,
    }
    if sections.get(L_WNOTES):
        spec["warranty"]["notes"] = sections[L_WNOTES].strip()

    sources = []
    for line in req(L_SOURCES).splitlines():
        line = line.strip().lstrip("-* ").strip()
        if not line:
            continue
        bits = [b.strip() for b in line.split("|")]
        src = {"url": bits[0].strip("<>")}
        if len(bits) > 1 and bits[1]:
            src["title"] = bits[1]
        if len(bits) > 2 and bits[2]:
            src["date"] = bits[2]
        sources.append(src)
    spec["sources"] = sources
    if sections.get(L_NOTES):
        spec["notes"] = sections[L_NOTES].strip()

    return spec, (sections.get(L_SPEC_ID) or "").strip() or None


def spec_from_json_block(body: str) -> tuple[dict, str | None]:
    after = body.split(MARKER, 1)[1]
    m = re.search(r"```json\s*\n(.*?)\n```", after, flags=re.DOTALL)
    if not m:
        raise SubmissionError("found the BatteryLedger marker but no ```json block after it")
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError as err:
        raise SubmissionError(f"JSON block is invalid: {err}") from None
    if not isinstance(data, dict):
        raise SubmissionError("JSON block must be an object")
    existing_id = data.get("id") if data.get("correction") else None
    return {k: v for k, v in data.items() if k in SUBMITTABLE}, existing_id


def _order(spec: dict) -> dict:
    keys = ["schema_version", "id", "spec_version", "brand", "series", "model", "variant", "regions",
            "chemistry", "phases", "capacity", "warranty", "sources", "notes",
            "submitted_by", "verified", "updated"]
    return {k: spec[k] for k in keys if k in spec}


def process(body: str, author: str) -> dict:
    if MARKER in body:
        spec, existing_id = spec_from_json_block(body)
    else:
        spec, existing_id = spec_from_form(parse_form_sections(body))

    all_specs = load_all_specs()
    by_id = {s["id"]: (p, s) for p, s in all_specs}

    if existing_id:
        if existing_id not in by_id:
            raise SubmissionError(f"no existing spec with ID '{existing_id}'")
        old_path, old = by_id[existing_id]
        spec["id"] = existing_id
        spec["spec_version"] = old["spec_version"] + 1
        action = "correction"
    else:
        spec["id"] = make_spec_id(spec["brand"], spec["model"], spec.get("variant"), spec["regions"])
        if spec["id"] in by_id:
            raise SubmissionError(
                f"a spec with ID '{spec['id']}' already exists. To change it, put that ID in "
                f"'{L_SPEC_ID}'."
            )
        spec["spec_version"] = 1
        action = "new"

    spec["schema_version"] = 1
    spec["submitted_by"] = author
    spec["verified"] = False
    spec["updated"] = date.today().isoformat()
    spec = _order(spec)

    path = spec_path(spec)
    errors = check_spec(spec, path)
    others = [(p, s) for p, s in all_specs if s["id"] != spec["id"]]
    errors += find_conflicts(spec, others)
    if action == "correction" and path != by_id[spec["id"]][0]:
        errors.append("a correction cannot change the brand (it would move the file)")
    if errors:
        raise SubmissionError("; ".join(errors))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    label = f"{spec['brand']} {spec['model']}" + (f" {spec['variant']}" if spec.get("variant") else "")
    return {
        "ok": True,
        "errors": [],
        "action": action,
        "spec_id": spec["id"],
        "path": str(path.relative_to(ROOT)),
        "title": f"{'Update' if action == 'correction' else 'Add'} {label} ({', '.join(spec['regions'])})",
        "summary": "```json\n" + json.dumps(spec, indent=2) + "\n```",
    }


def main() -> int:
    out = Path(sys.argv[1])
    body = os.environ.get("ISSUE_BODY", "")
    author = os.environ.get("ISSUE_AUTHOR", "")
    try:
        result = process(body, author)
    except SubmissionError as err:
        result = {"ok": False, "errors": [e.strip() for e in str(err).split(";")]}
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
