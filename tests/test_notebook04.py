"""
Runs lunar-hazard-map/04_shackleton.ipynb from top to bottom on a fake crater whose
shape we know (tests/synthetic_crater.py), then checks the notebook measured that
shape correctly and that its tether, Dock and radio answers obey the rules they must.

Slow (about 2 minutes). Skip with:  pytest -m "not slow"
"""
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    pytest.importorskip("rasterio")
    pytest.importorskip("skimage")
    nbformat = pytest.importorskip("nbformat")
    nbclient = pytest.importorskip("nbclient")
    import os
    import synthetic_crater

    base = tmp_path_factory.mktemp("nb04")
    data = synthetic_crater.make(base / "data")
    work = base / "lunar-hazard-map"
    work.mkdir()
    shutil.copy(ROOT / "lunar-hazard-map" / "04_shackleton.ipynb", work)

    nb = nbformat.read(work / "04_shackleton.ipynb", as_version=4)
    old = os.environ.get("LUNAR_DATA")
    os.environ["LUNAR_DATA"] = str(data)
    try:
        nbclient.NotebookClient(nb, timeout=1800, kernel_name="python3",
                                resources={"metadata": {"path": str(work)}}).execute()
    finally:
        if old is None:
            os.environ.pop("LUNAR_DATA", None)
        else:
            os.environ["LUNAR_DATA"] = old
    nbformat.write(nb, work / "04_executed.ipynb")
    return work, json.loads((work / "results" / "m4_summary.json").read_text())


def geo(summary, item):
    return next(r["measured"] for r in summary["measured"]["geometry"] if r["item"].startswith(item))


def test_runs_and_writes_every_output(run):
    work, s = run
    for f in ("M4_shackleton_geometry", "M4_hazard_map", "M4_rover_requirement", "M4_tether_profile",
              "M4_dock_trade", "M4_explorer_map"):
        assert (work / "figures" / f"{f}.png").exists(), f
    for k in ("route_km", "drop_km", "max_slope", "shadow_frac", "floor_area_km2", "floor_run_km", "floor_in_reach_frac"):
        assert k in s["design_inputs"], k


def test_measures_the_crater_we_built(run):
    import synthetic_crater as sc
    _, s = run
    assert geo(s, "Rim diameter") == pytest.approx(sc.TRUTH["rim_diameter_km"], abs=0.5)
    assert geo(s, "Depth") == pytest.approx(sc.TRUTH["depth_km"], abs=0.15)
    assert geo(s, "Floor pixels with a real laser shot") == pytest.approx(10, abs=1)


def test_finds_the_wall_too_steep_to_drive(run):
    import synthetic_crater as sc
    _, s = run
    assert s["measured"]["drive_down_deg_any_rim"] == pytest.approx(sc.TRUTH["steepest_wall_deg"], abs=3)


def test_tether_route_obeys_its_limits(run):
    _, s = run
    route = s["measured"]["tether_routes"][0]
    assert route["steepest_5m_deg"] <= 45.0 + 0.5            # T-REX limit
    assert route["length_3d_km"] >= route["map_length_km"]   # going downhill is longer than the map distance
    assert route["drop_m"] / 1000 == pytest.approx(s["design_inputs"]["drop_km"], abs=0.01)


def test_more_reach_covers_more_floor(run):
    _, s = run
    cover = [r["floor_in_reach_pct"] for r in s["measured"]["dock_reach"]]
    assert cover == sorted(cover) and 0 < cover[0] <= 100


def test_chosen_dock_is_the_best_candidate(run):
    _, s = run
    best = max(c["reach_pct_floor"] for c in s["measured"]["dock_candidates"])
    assert s["measured"]["dock_reach"][0]["floor_in_reach_pct"] >= best - 1.0


def test_sizing_script_reads_the_notebook(run, tmp_path):
    import subprocess
    import sys
    work, _ = run
    d = work.parent / "concept-sizing"
    d.mkdir(exist_ok=True)
    shutil.copy(ROOT / "concept-sizing" / "sizing.py", d)
    out = subprocess.run([sys.executable, "sizing.py"], cwd=d, capture_output=True, text=True, check=True).stdout
    assert "measured" in out.splitlines()[0]
    assert "measured by driving distance" in out
