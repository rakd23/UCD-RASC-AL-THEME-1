"""
Checks on concept-sizing/sizing.py.

Three kinds of test:
  * hand calculations: redo the physics with a calculator-style formula and compare
  * sanity rules: things that must always be true (more voltage = lighter tether, etc.)
  * reproduction: with the built-in Shackleton numbers, the script still gives the
    numbers quoted in the design doc
"""
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import sizing

ROOT = Path(__file__).resolve().parent.parent
G = 1.62


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    """Run sizing.py on its own (no notebook 04 output next to it), so it uses the
    built-in Shackleton numbers, and return results.json."""
    d = tmp_path_factory.mktemp("sizing") / "concept-sizing"
    d.mkdir()
    shutil.copy(ROOT / "concept-sizing" / "sizing.py", d)
    out = subprocess.run([sys.executable, "sizing.py"], cwd=d, capture_output=True, text=True, check=True)
    assert "built-in Shackleton values" in out.stdout
    return json.loads((d / "results.json").read_text())


# ---------------- 1. Tether ----------------

def test_tether_loses_at_most_10_percent():
    """Hand check: rebuild the wire resistance from the chosen wire size and
    confirm the power lost (I squared R) is 10% of the power delivered or less."""
    L_km, P, V = 13.6, 100.0, 1000.0
    t = sizing.tether(P, V, L_km, max_tension_N=350)
    A = sizing.ASSUME
    shade = sizing.SITE["shadow_frac"]
    rho = A["rho_al_293"] * ((1 - shade) * A["rho_al_hot_factor"] + shade * A["rho_al_cold_factor"])
    R_loop = rho * 2 * L_km * 1e3 / (t["A_cond_mm2"] * 1e-6)      # out and back
    loss = (P / V) ** 2 * R_loop
    assert loss <= 0.10 * P * 1.02


def test_higher_voltage_means_lighter_tether():
    for P in (100, 150, 200):
        masses = [sizing.tether(P, V, 13.6, 350)["mass_kg"] for V in (300, 600, 1000)]
        assert masses[0] > masses[1] > masses[2]


def test_more_power_means_heavier_tether():
    masses = [sizing.tether(P, 1000, 13.6, 350)["mass_kg"] for P in (100, 150, 200)]
    assert masses[0] < masses[1] < masses[2]


def test_strength_member_holds_worst_pull():
    """Hand check of the worst pull: ER plus a full spool on the steepest pitch."""
    er = sizing.with_growth(sizing.ER_ITEMS)
    t = sizing.sized_tether(100, 1000, 13.6, er)
    th = math.radians(sizing.SITE["max_slope"])
    pull = (er + t["mass_kg"]) * G * (math.sin(th) + 0.3 * math.cos(th))
    assert t["max_tension_N"] == pytest.approx(pull, rel=0.02)


# ---------------- 2. Explore Rover range ----------------

def test_range_equation_by_hand():
    """r = E (1 - R) / (2 w (c + h/v)), worked out step by step."""
    m = sizing.with_growth(sizing.ER_ITEMS)
    E = 2.4 * 3.6e6 * 0.8            # usable battery, J
    c = 0.15 * m * G / 0.5           # driving energy per metre, J/m
    h = 80 / 0.10                    # non-driving energy per metre at 0.10 m/s, J/m
    r = E * (1 - 0.20) / (2 * 1.3 * (c + h))
    assert sizing.er_range(0.10, 80, m)[0] == pytest.approx(r, rel=1e-9)
    assert h / (c + h) > 0.9         # staying warm and aware costs more than moving


def test_faster_or_warmer_reaches_further():
    m = sizing.with_growth(sizing.ER_ITEMS)
    reach = [sizing.er_range(v, 80, m)[0] for v in (0.05, 0.10, 0.15, 0.20)]
    assert reach == sorted(reach)
    assert sizing.er_range(0.10, 60, m)[0] > sizing.er_range(0.10, 80, m)[0]


# ---------------- 3. Whole run ----------------

def test_tether_feeds_more_than_the_er_uses(results):
    f = results["floor_campaign"]
    assert f["tether_Wh_per_cycle"] >= f["er_needs_Wh_per_cycle"]


def test_climb_out_energy_by_hand(results):
    m = sizing.with_growth(sizing.ER_ITEMS) + results["tether_baseline"]["mass_kg"] / 2
    s = results["site"]
    wh = m * G * (s["drop_km"] * 1e3 + 0.15 * s["route_km"] * 1e3) / 0.5 / 3600
    assert results["climb_out_Wh"] == pytest.approx(wh, abs=1)


def test_mass_budget_adds_up(results):
    m = results["mass"]
    parts = [v for k, v in m.items() if k != "TOTAL"]
    assert sum(p["with_growth_kg"] for p in parts) == pytest.approx(m["TOTAL"]["with_growth_kg"], abs=1)
    assert m["TOTAL"]["with_15pct_system_margin"] == pytest.approx(1.15 * m["TOTAL"]["with_growth_kg"], abs=1)


def test_deploy_rover_has_enough_sun(results):
    d = results["deploy_rover"]
    assert d["array_W"] > d["array_need_W"]


def test_reproduces_design_doc_numbers(results):
    """The baseline design doc (Nov 20 2026) was written from these numbers."""
    assert results["tether_length_km"] == pytest.approx(13.6, abs=0.1)
    assert results["tether_baseline"]["mass_kg"] == pytest.approx(129, abs=3)
    assert results["floor_campaign"]["reach_m"] == pytest.approx(2486, abs=10)
    assert results["mass"]["TOTAL"]["with_15pct_system_margin"] == pytest.approx(678, abs=5)
    assert results["cost_musd"]["low"] == pytest.approx(1309, abs=10)
