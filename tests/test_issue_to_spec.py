"""Tests for the submission parser. Run from repo root: pytest -q"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402
import issue_to_spec as its  # noqa: E402

FORM_BODY = """### Existing spec ID (corrections only)

_No response_

### Brand

Acme Energy

### Model

PowerStack

### Battery module

PowerStack 5

### Variant

_No response_

### Regions

AU, nz

### Chemistry

LFP

### Supported phases

- [X] Single phase
- [ ] Three phase

### Product type

Stackable module

### Nominal capacity per unit (kWh)

5.12

### Usable capacity per unit (kWh)

4.8

### Capacity reported by the inverter per unit (kWh)

_No response_

### Minimum units per system

2

### Maximum units per system

6

### Warranty period (years)

10

### Warranted end-of-life capacity (%)

60

### Throughput counted as

Discharged energy

### Throughput limit applies

Table by unit count

### Throughput limit (kWh)

_No response_

### Throughput table

2=28,000
3=42000

### Warranty notes

_No response_

### Sources

https://example.com/warranty.pdf | Warranty | 2025-01-31

### Other notes

_No response_

### Confirmation

- [X] The figures come from the manufacturer's documents linked above.
"""


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the scripts at a temporary copy of specs/."""
    specs = tmp_path / "specs"
    for src in common.SPECS_DIR.glob("*/*.json"):
        dst = specs / src.parent.name / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(src.read_text())
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(common, "SPECS_DIR", specs)
    monkeypatch.setattr(its, "ROOT", tmp_path)
    return specs


def test_form_new_spec(store):
    result = its.process(FORM_BODY, "someone")
    assert result["ok"] and result["action"] == "new"
    assert result["spec_id"] == "acme-energy-powerstack-5-anz"
    spec = json.loads((store / "acme-energy" / "acme-energy-powerstack-5-anz.json").read_text())
    assert spec["phases"] == ["1"]
    assert spec["series"] == "PowerStack"
    assert spec["regions"] == ["AU", "NZ"]
    assert spec["warranty"]["throughput"]["table"] == [
        {"units": 2, "kwh": 28000.0}, {"units": 3, "kwh": 42000.0}]
    assert spec["submitted_by"] == "someone" and spec["verified"] is False


def test_duplicate_new_is_rejected(store):
    its.process(FORM_BODY, "someone")
    with pytest.raises(its.SubmissionError, match="already exists"):
        its.process(FORM_BODY, "someone")


def test_json_correction_bumps_version(store):
    existing = json.loads((store / "sigenergy" / "sigenergy-sigenstor-bat-8-0-anz.json").read_text())
    payload = {k: existing[k] for k in its.SUBMITTABLE if k in existing}
    payload["warranty"]["throughput"]["basis"] = "discharged"
    payload.update({"id": existing["id"], "correction": True,
                    "submitted_by": "spoofed", "verified": True})
    body = f"Submitted from BatteryLedger\n\n{its.MARKER}\n```json\n{json.dumps(payload)}\n```\n"
    result = its.process(body, "realuser")
    assert result["action"] == "correction"
    spec = json.loads((store / "sigenergy" / f"{existing['id']}.json").read_text())
    assert spec["spec_version"] == existing["spec_version"] + 1
    assert spec["warranty"]["throughput"]["basis"] == "discharged"
    assert spec["submitted_by"] == "realuser" and spec["verified"] is False


def test_bad_input_reports_errors(store):
    body = FORM_BODY.replace("- [X] Single phase", "- [ ] Single phase")
    with pytest.raises(its.SubmissionError, match="phase"):
        its.process(body, "someone")
    body = FORM_BODY.replace("https://example.com/warranty.pdf", "http://insecure.example")
    with pytest.raises(its.SubmissionError, match="sources"):
        its.process(body, "someone")
