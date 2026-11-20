# UCD RASC-AL 2027 · Theme 1

Analysis code for the Aggie Space Initiative's NASA RASC-AL 2027 Theme 1 proposal (Enabling Extreme Exploration). The concept is a **tethered crater explorer**:

1. A solar **Deploy Rover (DR)** lands on a sunlit crater rim and anchors.
2. An **Explore Rover (ER)** rappels into the permanently shadowed crater on a power-and-data tether.
3. On the floor the ER sets a charging **Dock** at the tether's end, then maps buried ice in battery-powered trips.
4. When the crater is done, the ER reels itself back up, and the DR carries it along the lit ridge to the next crater.

First target: Shackleton.

## How the pieces fit

```
NASA LOLA maps ──> lunar-hazard-map/ ──> results/m4_summary.json ──> concept-sizing/sizing.py ──> results.json ──> figures/conops.png
                   (where can we drive?    (tether route, Dock site,    (how heavy, how far,                         (proposal figure)
                    where does the          floor in reach)              how long, how much?)
                    tether go?)
                                    rover-comms/  (can the ER radio the Dock from here?)
```

| Folder | Question it answers | Start here |
| --- | --- | --- |
| [`lunar-hazard-map/`](lunar-hazard-map/) | Where is the terrain safe, steep or impossible? Where does the tether go down Shackleton's wall, and where should the Dock sit? | Notebooks `01` → `04` |
| [`concept-sizing/`](concept-sizing/) | How long and heavy is the tether? How far can the ER drive per charge? How long does a crater take? What does the system weigh and cost? | `python sizing.py` |
| [`rover-comms/`](rover-comms/) | Which way does the ER point its antenna, and does terrain block the link to the Dock? | `python simple_comm_angle.py` |

## Run order

1. `lunar-hazard-map`: run notebooks 01–04 (data download steps are in its README).
2. `concept-sizing`: `python sizing.py`, then `python conops_fig.py`. These pick up notebook 04's measurements automatically.
3. `rover-comms`: run on any two points, e.g. an ER position and the Dock site from `m4_summary.json`.

Data: NASA LRO LOLA products from NASA Goddard's PGDA (Barker et al. 2021, 2023; citations in each folder).
