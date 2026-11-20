"""
A fake Shackleton with a known shape, written as the same files notebook 04 reads
(same names, projection and pixel sizes as NASA's). Because we built it, we know
the right answers, so the notebook can be checked against them.

Built-in shape: rim radius 10.4 km (+/- 0.25 km), depth 4.1 km plus a 180 m raised rim,
floor radius about 3 km, smooth wall whose steepest point is about 40 degrees,
four small floor craters. 10% of pixels are marked as having a laser shot.

Run alone:  python synthetic_crater.py OUTPUT_FOLDER
"""
import sys
from pathlib import Path

import numpy as np

MOON_R = 1_737_400.0
CRS = "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +x_0=0 +y_0=0 +R=1737400 +units=m +no_defs"
LAT, LON = -89.67, 129.78                      # same Shackleton centre the notebook uses
RHO = 2 * MOON_R * np.tan(np.radians(90 + LAT) / 2)
CX, CY = RHO * np.sin(np.radians(LON)), RHO * np.cos(np.radians(LON))

TRUTH = dict(rim_diameter_km=20.8, depth_km=4.28, steepest_wall_deg=40.0, rim_radius_km=10.4)


def terrain(X, Y):
    r = np.hypot(X - CX, Y - CY)
    az = np.arctan2(X - CX, Y - CY)
    rim_r = 10_400 + 250 * np.sin(3 * az)
    floor_r = 3_050 + 150 * np.cos(2 * az)
    s = np.clip((r - floor_r) / (rim_r - floor_r), 0, 1)
    z = -4_100 * (1 - (3 * s**2 - 2 * s**3))                        # smooth bowl
    z += 180 * np.exp(-((r - rim_r) / 500) ** 2)                     # raised rim
    z += np.where(r > rim_r, -0.03 * (r - rim_r), 0)                 # gentle outer slope
    for dx, dy, rr, d in [(1200, -900, 300, 45), (-1500, 700, 220, 35), (400, 1800, 160, 30), (-600, -1700, 250, 40)]:
        q = np.hypot(X - CX - dx, Y - CY - dy) / rr
        z += np.where(q < 1, -d * (1 - q**2), 0) + 12 * np.exp(-((q - 1) / 0.15) ** 2)   # small floor craters
    z += 25 * np.sin(X / 900.0) * np.cos(Y / 1300.0)                 # gentle undulation
    return z.astype("float32")


def make(out, seed=4):
    import rasterio
    from rasterio.transform import from_origin

    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)

    half5 = 17_000
    x0 = np.floor((CX - half5) / 5) * 5
    y0 = np.ceil((CY + half5) / 5) * 5
    n = int(2 * half5 / 5)
    xs = x0 + (np.arange(n) + 0.5) * 5
    ys = y0 - (np.arange(n) + 0.5) * 5
    prof = dict(driver="GTiff", height=n, width=n, count=1, crs=CRS, transform=from_origin(x0, y0, 5, 5),
                tiled=True, blockxsize=512, blockysize=512, compress="deflate")
    with rasterio.open(out / "ldem_87s_5mpp.tif", "w", dtype="float32", nodata=-9999, **prof) as d, \
         rasterio.open(out / "ldec_87s_5mpp.tif", "w", dtype="int16", nodata=-1, **prof) as dc:
        for i in range(0, n, 512):
            Y, X = np.meshgrid(ys[i:i + 512], xs, indexing="ij")
            w = rasterio.windows.Window(0, i, n, Y.shape[0])
            d.write(terrain(X, Y) + rng.normal(0, 0.4, X.shape).astype("float32"), 1, window=w)
            dc.write((rng.random(X.shape) < 0.1).astype("int16"), 1, window=w)

    half20 = 20_000
    m = int(2 * half20 / 20)
    x20 = np.floor((CX - half20) / 20) * 20
    y20 = np.ceil((CY + half20) / 20) * 20
    Y, X = np.meshgrid(y20 - (np.arange(m) + 0.5) * 20, x20 + (np.arange(m) + 0.5) * 20, indexing="ij")
    r = np.hypot(X - CX, Y - CY)
    az = np.degrees(np.arctan2(X - CX, Y - CY))
    psr = (r < 7_000) | ((r < 9_800) & ((az > 60) | (az < -150)))   # floor and part of the wall in shadow
    with rasterio.open(out / "LPSR_80S_20MPP_ADJ.TIF", "w", driver="GTiff", height=m, width=m, count=1,
                       dtype="uint8", crs=CRS, transform=from_origin(x20, y20, 20, 20)) as d:
        d.write(psr.astype("uint8"), 1)
    return out


if __name__ == "__main__":
    print("wrote", make(sys.argv[1] if len(sys.argv) > 1 else "synthetic_data"))
