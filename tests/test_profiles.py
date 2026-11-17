"""Sensor profile validation tests. Run from repo root: pytest -q"""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import common  # noqa: E402


def _profiles():
    return {p["id"]: p for _, p in common.load_all_profiles()}


def test_seed_profiles_valid():
    for path, profile in common.load_all_profiles():
        assert common.check_profile(profile, path) == []


def test_module_role_requires_serial():
    p = copy.deepcopy(_profiles()["sigenergy2mqtt"])
    p["roles"]["module_soc"] = [{"level": "module", "unique_id": "{prefix}_{plant}_battery_soc"}]
    assert any("module_soc" in e for e in common.check_profile(p))


def test_template_rules():
    p = copy.deepcopy(_profiles()["sigen-local-modbus"])
    p["roles"]["soh"] = [{"level": "plant", "unique_id": "{entry}_{entry}_plant_ess_soh"}]
    assert any("only once" in e for e in common.check_profile(p))
    p["roles"]["soh"] = [{"level": "plant", "unique_id": "fixed_plant_ess_soh"}]
    assert common.check_profile(p) == []  # fixed unique IDs are fine (e.g. Energy Manager)
    p["roles"]["soh"] = [{"level": "plant", "unique_id": "{entry}_{bogus}_soh"}]
    assert common.check_profile(p)


def test_energy_manager_any_brand_and_install_date():
    p = _profiles()["energy-manager"]
    assert p["brands"] == ["*"]
    assert p["roles"]["install_date"][0]["platform"] == "input_datetime"
