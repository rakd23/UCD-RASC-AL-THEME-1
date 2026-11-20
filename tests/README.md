# Tests: how we know the code works

```zsh
conda activate geoai
conda install -c conda-forge pytest nbclient nbformat ipykernel pyproj -y   # once
cd ~/UCD-RASC-AL-THEME-1
pytest                    # everything, about 2 minutes
pytest -m "not slow"      # skip the notebook run, under 5 seconds
```

A good run ends with `26 passed`. The same tests run on GitHub after every push (the **Actions** tab), so the repo shows a green check when the code works.

## The idea

You can't check a lunar map against the Moon, so each test compares the code to an answer we already know by a different route:

1. **Hand calculations.** Redo the physics with the formula written out, and compare.
2. **Geometry with a known answer.** Shapes where the right answer comes from textbook geometry, like how far two antennas on a smooth Moon can see.
3. **A fake crater we built ourselves.** `synthetic_crater.py` writes a Shackleton look-alike with a shape we chose, in the same file format and projection as NASA's. Notebook 04 runs on it end to end, and we check it measures what we built.
4. **Rules that must always hold.** For example, more voltage always means a lighter tether.

We also checked that the tests can fail. With planted bugs (halving the range equation's "out and back" factor, tripling the allowed tether resistance, using the wrong Moon radius), 4 sizing tests and 4 comms tests went red.

## What each test proves

**`test_sizing.py`** (concept-sizing)

| Test | Known answer it's checked against |
| --- | --- |
| Tether loses at most 10% | Rebuild the wire's resistance from its size; current² × resistance ≤ 10% of the power |
| Higher voltage = lighter; more power = heavier | Must always be true |
| Strength member holds worst pull | ER + full spool on the 41° pitch, worked out by hand |
| Range equation by hand | r = E(1 − R) / (2w(c + h/v)), every term typed out |
| Faster or warmer reaches further | Must always be true |
| Tether feeds more than the ER uses | Energy in ≥ energy out, every charge cycle |
| Climb-out energy by hand | m·g·height + rolling resistance, ÷ efficiency |
| Mass budget adds up | Parts sum to the total; +15% system margin |
| Deploy Rover has enough sun | Array output > what it needs |
| Reproduces the design doc | With built-in Shackleton numbers: 13.6 km and ~129 kg tether, 2,486 m reach, ~678 kg landed, ~$1.31B low cost |

**`test_comms.py`** (rover-comms)

| Test | Known answer |
| --- | --- |
| Projection round trip | Map coordinates → lat/lon → back gives the same point |
| Matches pyproj | Same map coordinates as the standard projection library |
| Target dips below horizon | On a smooth sphere, a target d away sits d/(2R) radians below level |
| Radio horizon | Two 1 m antennas see each other out to about 3.73 km: clear at 3 km, blocked at 4.5 km |
| 10° slope | Facing uphill the rover pitches 10°; facing sideways it rolls 10° |
| Hill blocks the Dock | Open-floor link clear; link behind the 120 m hill blocked by more than 50 m |
| GeoTIFF = memory | Reading the map from a file gives the same answer as from memory |

**`test_notebook04.py`** (lunar-hazard-map, slow)

| Test | Known answer |
| --- | --- |
| Runs and writes every output | All six M4 figures and the `design_inputs` block exist |
| Measures the crater we built | Diameter 20.8 km ± 0.5, depth 4.28 km ± 0.15, 10% laser-shot pixels |
| Wall too steep to drive | The fake wall's steepest point is built at about 40°; the notebook must find 40° ± 3 |
| Tether route obeys its limits | Never steeper than 45° (T-REX); 3D length ≥ map length; drop matches |
| More reach covers more floor | Must always be true |
| Chosen Dock is the best candidate | Within 1 point of the best site tried |
| Sizing reads the notebook | `sizing.py` picks up the notebook's measurements |

## On the real data

The tests prove the code does what it says on a crater we understand. On the real 5 m map, Section A of notebook 04 is the check: Shackleton's measured diameter and depth sit next to the published values (20.7 vs 21 km, 4.07 vs 4.2 km in the last run).
