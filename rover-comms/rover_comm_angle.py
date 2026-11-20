"""
rover_comm_angle.py
Antenna pointing angles and terrain line-of-sight for a small scout rover
talking to a hub, relay beacon, or the rim tower (Lantern concept, RASC-AL 2027 Theme 1).

What it computes for a link from the rover antenna (A) to a target antenna (B):
  1. Slant range                       - straight-line distance, metres
  2. Azimuth                           - compass direction to B, degrees clockwise from local north
  3. Elevation angle                   - how far above the local horizon B appears, degrees
                                          (includes the Moon's curvature)
  4. Gimbal pan / tilt                 - the same direction expressed in the rover's own body
                                          frame, after accounting for heading and the pitch/roll
                                          the rover gets from sitting on a slope
  5. Line of sight + Fresnel clearance - whether the terrain between A and B blocks the beam,
                                          checked against a LOLA elevation map (DEM)

Coordinates follow the LOLA south-pole GeoTIFFs from PGDA: south polar stereographic
metres on a 1737.4 km sphere, elevations in metres relative to that sphere.

Usage
  python rover_comm_angle.py --demo                      # synthetic crater, no data needed
  python rover_comm_angle.py --dem LDEM_80S_20M.tif \
      --rover 1200 -3400 --target 5600 -900 \
      --rover-mast 0.5 --target-mast 30 --heading 45 --freq 2.4e9 --plot link.png

Every rover/tower number in this file (mast heights, wheelbase, frequency) is a
placeholder for the team to replace once the scout and tower are sized.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np

R_MOON = 1_737_400.0       # m, LOLA reference sphere
C_LIGHT = 299_792_458.0    # m/s


# ---------------------------------------------------------------------------
# 1. Map coordinates <-> 3D Moon-centred coordinates
# ---------------------------------------------------------------------------
# South polar stereographic, true scale at the pole (lat_0 = -90, lon_0 = 0, k = 1):
#   rho = 2R tan(pi/4 + lat/2),  x = rho sin(lon),  y = rho cos(lon)

def stereo_to_latlon(x, y):
    rho = np.hypot(x, y)
    lat = 2.0 * np.arctan(rho / (2.0 * R_MOON)) - np.pi / 2.0
    lon = np.arctan2(x, y)
    return lat, lon


def latlon_to_stereo(lat, lon):
    rho = 2.0 * R_MOON * np.tan(np.pi / 4.0 + lat / 2.0)
    return rho * np.sin(lon), rho * np.cos(lon)


def latlon_h_to_xyz(lat, lon, h):
    r = R_MOON + h
    return np.stack([r * np.cos(lat) * np.cos(lon),
                     r * np.cos(lat) * np.sin(lon),
                     r * np.sin(lat)], axis=-1)


def xyz_to_latlon_h(p):
    p = np.asarray(p, dtype=float)
    r = np.linalg.norm(p, axis=-1)
    lat = np.arcsin(p[..., 2] / r)
    lon = np.arctan2(p[..., 1], p[..., 0])
    return lat, lon, r - R_MOON


def enu_basis(lat, lon):
    """Unit vectors east, north, up at a surface point (up = sphere normal)."""
    e = np.array([-math.sin(lon), math.cos(lon), 0.0])
    n = np.array([-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)])
    u = np.array([math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)])
    return e, n, u


# ---------------------------------------------------------------------------
# 2. Elevation map with bilinear lookup
# ---------------------------------------------------------------------------

@dataclass
class Dem:
    z: np.ndarray       # elevation grid, metres (NaN = no data)
    x0: float           # x of the left edge of column 0
    y0: float           # y of the top edge of row 0
    dx: float           # pixel width (positive)
    dy: float           # pixel height (positive; rows run top to bottom, y decreasing)

    def height(self, x, y):
        """Bilinear elevation at map coordinates (x, y). NaN outside the grid."""
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        c = (x - self.x0) / self.dx - 0.5
        r = (self.y0 - y) / self.dy - 0.5
        c0 = np.floor(c).astype(int)
        r0 = np.floor(r).astype(int)
        fc, fr = c - c0, r - r0
        rows, cols = self.z.shape
        ok = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < cols) & (r0 + 1 < rows)
        c0s, r0s = np.clip(c0, 0, cols - 2), np.clip(r0, 0, rows - 2)
        z00 = self.z[r0s, c0s]
        z01 = self.z[r0s, c0s + 1]
        z10 = self.z[r0s + 1, c0s]
        z11 = self.z[r0s + 1, c0s + 1]
        out = (z00 * (1 - fc) * (1 - fr) + z01 * fc * (1 - fr)
               + z10 * (1 - fc) * fr + z11 * fc * fr)
        return np.where(ok, out, np.nan)

    @classmethod
    def from_geotiff(cls, path, bounds=None, margin=2000.0):
        """Read a LOLA GeoTIFF. With bounds=(xmin, ymin, xmax, ymax) only that window
        (plus a margin) is read, so multi-GB files never load whole."""
        import rasterio
        from rasterio.windows import from_bounds

        with rasterio.open(path) as src:
            if bounds is None:
                window = None
            else:
                xmin, ymin, xmax, ymax = bounds
                window = from_bounds(xmin - margin, ymin - margin, xmax + margin, ymax + margin,
                                     src.transform).round_offsets().round_lengths()
            z = src.read(1, window=window, masked=True).astype(float).filled(np.nan)
            t = src.window_transform(window) if window is not None else src.transform
            scale = (src.scales[0] if src.scales else 1.0) or 1.0
            offset = (src.offsets[0] if src.offsets else 0.0) or 0.0
        z = z * scale + offset
        # Some LOLA products store elevation in km. Convert if values look like km.
        if np.nanmax(np.abs(z)) < 50:
            z = z * 1000.0
        return cls(z=z, x0=t.c, y0=t.f, dx=t.a, dy=-t.e)


# ---------------------------------------------------------------------------
# 3. Pointing angles
# ---------------------------------------------------------------------------

@dataclass
class LinkResult:
    slant_range_m: float
    azimuth_deg: float          # clockwise from local north
    map_bearing_deg: float      # clockwise from map +y (grid north), for the Leaflet viewer
    elevation_deg: float        # above the local horizon at the rover
    pan_deg: float              # gimbal pan, clockwise from rover's nose
    tilt_deg: float             # gimbal tilt, above the rover deck plane
    rover_pitch_deg: float
    rover_roll_deg: float
    line_of_sight: bool
    min_clearance_m: float      # smallest gap between beam and terrain (negative = blocked)
    min_fresnel_ratio: float    # clearance / first Fresnel radius (>= 0.6 is the usual target)
    worst_point_xy: tuple       # map position of the tightest spot (lowest Fresnel ratio)
    profile: dict               # sampled data for plotting


def rover_attitude(dem, x, y, heading_deg, wheelbase=0.6, track=0.5):
    """Pitch (nose up +) and roll (right side down +) of a rover sitting on the DEM.
    Wheelbase and track are placeholder scout dimensions in metres."""
    lat, lon = stereo_to_latlon(x, y)
    e, n, u = enu_basis(float(lat), float(lon))
    psi = math.radians(heading_deg)
    fwd = math.sin(psi) * e + math.cos(psi) * n
    left = -math.cos(psi) * e + math.sin(psi) * n
    p0 = latlon_h_to_xyz(lat, lon, 0.0)

    def ground(offset_vec):
        la, lo, _ = xyz_to_latlon_h(p0 + offset_vec)
        gx, gy = latlon_to_stereo(la, lo)
        return float(dem.height(gx, gy))

    z_f, z_b = ground(fwd * wheelbase / 2), ground(-fwd * wheelbase / 2)
    z_l, z_r = ground(left * track / 2), ground(-left * track / 2)
    pitch = math.degrees(math.atan2(z_f - z_b, wheelbase))
    roll = math.degrees(math.atan2(z_l - z_r, track))
    return pitch, roll


def body_angles(v_enu, heading_deg, pitch_deg, roll_deg):
    """Express an east-north-up direction in the rover body frame.
    Returns (pan clockwise from the nose, tilt above the deck), in degrees."""
    psi, th, ph = map(math.radians, (heading_deg, pitch_deg, roll_deg))
    f = np.array([math.sin(psi), math.cos(psi), 0.0])
    l = np.array([-math.cos(psi), math.sin(psi), 0.0])
    u = np.array([0.0, 0.0, 1.0])
    f, u = f * math.cos(th) + u * math.sin(th), u * math.cos(th) - f * math.sin(th)   # pitch
    l, u = l * math.cos(ph) + u * math.sin(ph), u * math.cos(ph) - l * math.sin(ph)   # roll
    vf, vl, vu = v_enu @ f, v_enu @ l, v_enu @ u
    pan = round(math.degrees(math.atan2(-vl, vf)), 9) % 360.0
    tilt = math.degrees(math.asin(np.clip(vu, -1, 1)))
    return pan, tilt


def link_angles(dem, rover_xy, target_xy, rover_mast=0.5, target_mast=30.0,
                heading_deg=0.0, freq_hz=2.4e9, step_m=None,
                wheelbase=0.6, track=0.5):
    """Full link analysis from a rover antenna to a target antenna."""
    (xa, ya), (xb, yb) = rover_xy, target_xy
    za = float(dem.height(xa, ya)) + rover_mast
    zb = float(dem.height(xb, yb)) + target_mast
    if not (np.isfinite(za) and np.isfinite(zb)):
        raise ValueError("Rover or target is outside the DEM or on a no-data pixel.")

    lat_a, lon_a = stereo_to_latlon(xa, ya)
    lat_b, lon_b = stereo_to_latlon(xb, yb)
    A = latlon_h_to_xyz(lat_a, lon_a, za)
    B = latlon_h_to_xyz(lat_b, lon_b, zb)
    AB = B - A
    rng = float(np.linalg.norm(AB))
    d = AB / rng

    # Direction in the rover's local east-north-up frame
    e, n, u = enu_basis(float(lat_a), float(lon_a))
    v_enu = np.array([d @ e, d @ n, d @ u])
    az = math.degrees(math.atan2(v_enu[0], v_enu[1])) % 360.0
    el = math.degrees(math.asin(np.clip(v_enu[2], -1, 1)))
    bearing = math.degrees(math.atan2(xb - xa, yb - ya)) % 360.0

    pitch, roll = rover_attitude(dem, xa, ya, heading_deg, wheelbase, track)
    pan, tilt = body_angles(v_enu, heading_deg, pitch, roll)

    # Line of sight: walk the straight 3D beam, compare its height with the ground below it
    step = step_m or max(dem.dx / 2, 1.0)
    t = np.linspace(0.0, 1.0, max(int(rng / step), 50))
    P = A[None, :] + t[:, None] * AB[None, :]
    lat_p, lon_p, h_beam = xyz_to_latlon_h(P)
    px, py = latlon_to_stereo(lat_p, lon_p)
    h_ground = dem.height(px, py)
    gap_vertical = h_beam - h_ground
    gap = gap_vertical * math.cos(math.radians(el))        # approx. perpendicular to the beam

    # First Fresnel zone radius: F1 = sqrt(lambda * d1 * d2 / (d1 + d2))
    lam = C_LIGHT / freq_hz
    d1, d2 = t * rng, (1 - t) * rng
    f1 = np.sqrt(lam * d1 * d2 / rng)

    inner = slice(1, -1)                                    # skip the two antenna endpoints
    g, f = gap[inner], f1[inner]
    valid = np.isfinite(g)
    ratio = np.where(valid & (f > 0), g / np.where(f > 0, f, 1), np.inf)
    i_min = int(np.argmin(ratio))           # tightest spot relative to the Fresnel zone

    return LinkResult(
        slant_range_m=rng,
        azimuth_deg=az,
        map_bearing_deg=bearing,
        elevation_deg=el,
        pan_deg=pan,
        tilt_deg=tilt,
        rover_pitch_deg=pitch,
        rover_roll_deg=roll,
        line_of_sight=bool(np.nanmin(g) > 0),
        min_clearance_m=float(np.nanmin(g)),
        min_fresnel_ratio=float(np.min(ratio)),
        worst_point_xy=(float(px[inner][i_min]), float(py[inner][i_min])),
        profile=dict(dist=t * rng, beam=h_beam, ground=h_ground, f1=f1, el=el,
                     worst=i_min + 1, worst_gap=float(g[i_min])),
    )


def angles_along_route(dem, route_xy, target_xy, **kw):
    """Run link_angles at every waypoint of a planned route (e.g. the A* output).
    Heading at each waypoint is taken from the direction of travel. The first waypoint
    whose Fresnel ratio drops below 0.6 is where a relay beacon should be dropped."""
    out = []
    for i, (x, y) in enumerate(route_xy):
        j = min(i + 1, len(route_xy) - 1)
        k = i - 1 if j == i else i
        hx, hy = route_xy[j][0] - route_xy[k][0], route_xy[j][1] - route_xy[k][1]
        heading = math.degrees(math.atan2(hx, hy)) % 360.0     # map-grid heading
        lat, lon = stereo_to_latlon(x, y)
        heading = (heading - math.degrees(float(lon))) % 360.0  # grid -> local north (south-polar stereo)
        out.append(link_angles(dem, (x, y), target_xy, heading_deg=heading, **kw))
    return out


# ---------------------------------------------------------------------------
# 4. Output helpers
# ---------------------------------------------------------------------------

def report(res: LinkResult, label="Link"):
    status = "CLEAR" if res.line_of_sight else "BLOCKED"
    if not res.line_of_sight:
        fres = "beam blocked by terrain"
    elif res.min_fresnel_ratio >= 0.6:
        fres = "ok"
    else:
        fres = "beam clears, but terrain intrudes on the Fresnel zone (extra signal loss)"
    print(f"\n{label}")
    print(f"  slant range        {res.slant_range_m / 1000:9.3f} km")
    print(f"  azimuth            {res.azimuth_deg:9.2f} deg  (from local north)")
    print(f"  map bearing        {res.map_bearing_deg:9.2f} deg  (from grid +y)")
    print(f"  elevation angle    {res.elevation_deg:9.2f} deg  (above local horizon)")
    print(f"  rover pitch / roll {res.rover_pitch_deg:6.2f} / {res.rover_roll_deg:.2f} deg")
    print(f"  gimbal pan / tilt  {res.pan_deg:6.2f} / {res.tilt_deg:.2f} deg  (rover body frame)")
    print(f"  line of sight      {status}, min clearance {res.min_clearance_m:.1f} m")
    print(f"  tightest spot      {res.profile['worst_gap']:.1f} m clearance at map "
          f"({res.worst_point_xy[0]:.0f}, {res.worst_point_xy[1]:.0f})")
    print(f"  Fresnel clearance  {res.min_fresnel_ratio:.2f} x F1  ({fres})")


def plot_profile(res: LinkResult, path, title="Rover link profile"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    p = res.profile
    d = p["dist"] / 1000
    # Draw relative to the chord between endpoints so curvature shows as the ground bending
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.fill_between(d, np.nanmin(p["ground"]) - 200, p["ground"], color="#8a8a8a", alpha=0.6,
                    label="terrain (DEM)")
    ax.plot(d, p["beam"], color="#1f6feb", lw=2, label="beam (straight line)")
    ax.fill_between(d, p["beam"] - p["f1"] * 0.6, p["beam"] + p["f1"] * 0.6,
                    color="#1f6feb", alpha=0.15, label="60% of 1st Fresnel zone")
    i = p["worst"]
    ax.scatter([d[i]], [p["ground"][i]], color="#d1242f", zorder=5,
               label=f"tightest spot ({p['worst_gap']:.0f} m clearance)")
    ax.annotate(f"elevation {res.elevation_deg:.1f}°", (d[0], p["beam"][0]),
                xytext=(10, -18), textcoords="offset points")
    ax.set_xlabel("distance from rover (km)")
    ax.set_ylabel("height above 1737.4 km sphere (m)")
    ax.set_title(f"{title}: {'line of sight CLEAR' if res.line_of_sight else 'BLOCKED'}")
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Synthetic demo (no data download needed)
# ---------------------------------------------------------------------------

def synthetic_crater(center=(0.0, 10_000.0), radius=10_500.0, depth=4_000.0,
                     floor_radius=3_300.0, px=20.0, half=16_000.0):
    """Bowl crater roughly Shackleton-sized, plus one 120 m hill on the floor.
    Illustrative terrain only, not a real map."""
    cx, cy = center
    xs = np.arange(cx - half, cx + half, px) + px / 2
    ys = np.arange(cy + half, cy - half, -px) - px / 2
    X, Y = np.meshgrid(xs, ys)
    r = np.hypot(X - cx, Y - cy)
    s = np.clip((r - floor_radius) / (radius - floor_radius), 0, 1)
    z = -depth + depth * (3 * s**2 - 2 * s**3)                 # smooth wall
    z += 200 * np.exp(-((r - radius) / 350) ** 2)               # raised rim
    z += 120 * np.exp(-(((X - (cx + 1500)) ** 2 + (Y - (cy - 800)) ** 2) / 300**2))  # floor hill
    return Dem(z=z, x0=xs[0] - px / 2, y0=ys[0] + px / 2, dx=px, dy=px)


def demo(plot_prefix="demo"):
    dem = synthetic_crater()
    tower = (0.0, 10_000.0 + 10_480.0)       # on the rim crest
    hub = (0.0 + 3_000.0, 10_000.0 - 1_400.0)  # on the floor, behind the hill
    rover = (-1_000.0, 10_000.0 - 400.0)

    print("Synthetic Shackleton-sized crater, 20 m pixels (illustrative terrain).")
    r1 = link_angles(dem, rover, tower, rover_mast=0.5, target_mast=30.0, heading_deg=30)
    report(r1, "Scout -> rim tower (30 m mast, placeholder)")
    plot_profile(r1, f"{plot_prefix}_tower.png", "Scout to rim tower")

    r2 = link_angles(dem, rover, hub, rover_mast=0.5, target_mast=2.0, heading_deg=30)
    report(r2, "Scout -> floor hub behind a 120 m hill")
    plot_profile(r2, f"{plot_prefix}_hub.png", "Scout to floor hub")


# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="run on a synthetic crater")
    ap.add_argument("--dem", help="LOLA GeoTIFF (south polar stereographic)")
    ap.add_argument("--rover", nargs=2, type=float, metavar=("X", "Y"))
    ap.add_argument("--target", nargs=2, type=float, metavar=("X", "Y"))
    ap.add_argument("--rover-mast", type=float, default=0.5, help="m above ground (placeholder)")
    ap.add_argument("--target-mast", type=float, default=30.0, help="m above ground (placeholder)")
    ap.add_argument("--heading", type=float, default=0.0, help="rover heading, deg from local north")
    ap.add_argument("--freq", type=float, default=2.4e9, help="radio frequency, Hz (placeholder)")
    ap.add_argument("--plot", help="save a terrain profile PNG here")
    a = ap.parse_args()

    if a.demo or not a.dem:
        demo()
        return
    xs, ys = (a.rover[0], a.target[0]), (a.rover[1], a.target[1])
    dem = Dem.from_geotiff(a.dem, bounds=(min(xs), min(ys), max(xs), max(ys)))
    res = link_angles(dem, tuple(a.rover), tuple(a.target), a.rover_mast, a.target_mast,
                      a.heading, a.freq)
    report(res)
    if a.plot:
        plot_profile(res, a.plot)


if __name__ == "__main__":
    main()
