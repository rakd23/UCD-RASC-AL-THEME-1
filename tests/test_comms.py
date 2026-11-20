"""
Checks on rover-comms/rover_comm_angle.py against answers known from geometry.
"""
import math

import numpy as np
import pytest

import rover_comm_angle as rc

R = 1_737_400.0   # the Moon radius LOLA uses, typed in here so a wrong value in the code gets caught


def flat_moon(half=12_000.0, px=10.0, y_center=20_000.0):
    """A perfectly smooth Moon (height 0 everywhere) around a point near the south pole."""
    xs = np.arange(-half, half, px) + px / 2
    ys = np.arange(y_center + half, y_center - half, -px) - px / 2
    return rc.Dem(z=np.zeros((len(ys), len(xs))), x0=xs[0] - px / 2, y0=ys[0] + px / 2, dx=px, dy=px)


def test_projection_round_trip():
    lat, lon = math.radians(-89.67), math.radians(129.78)
    x, y = rc.latlon_to_stereo(lat, lon)
    lat2, lon2 = rc.stereo_to_latlon(x, y)
    assert lat2 == pytest.approx(lat, abs=1e-12) and lon2 == pytest.approx(lon, abs=1e-12)


def test_projection_matches_pyproj():
    pyproj = pytest.importorskip("pyproj")
    t = pyproj.Transformer.from_crs("+proj=longlat +R=1737400 +no_defs",
                                    "+proj=stere +lat_0=-90 +lon_0=0 +k=1 +R=1737400 +units=m +no_defs", always_xy=True)
    x_ref, y_ref = t.transform(129.78, -89.67)
    x, y = rc.latlon_to_stereo(math.radians(-89.67), math.radians(129.78))
    assert x == pytest.approx(x_ref, abs=1e-3) and y == pytest.approx(y_ref, abs=1e-3)


def test_target_dips_below_horizon_by_curvature():
    """On a smooth sphere, a target at distance d sits d / (2R) radians below the horizon."""
    dem = flat_moon()
    d = 8_000.0
    res = rc.link_angles(dem, (0.0, 20_000.0), (0.0, 20_000.0 + d), rover_mast=0.0, target_mast=0.0)
    assert res.elevation_deg == pytest.approx(-math.degrees(d / (2 * R)), abs=0.005)


@pytest.mark.parametrize("distance_m, should_see", [(3_000.0, True), (4_500.0, False)])
def test_radio_horizon(distance_m, should_see):
    """Two 1 m antennas on a smooth Moon can see each other out to
    sqrt(2 R h1) + sqrt(2 R h2), about 3.73 km. Closer = clear, farther = blocked."""
    horizon = 2 * math.sqrt(2 * R * 1.0)
    assert (distance_m < horizon) == should_see
    dem = flat_moon()
    res = rc.link_angles(dem, (0.0, 20_000.0), (0.0, 20_000.0 - distance_m), rover_mast=1.0, target_mast=1.0)
    assert res.line_of_sight == should_see


def test_rover_on_a_10_degree_slope():
    """Ground rising 10 degrees toward local north: facing north the rover pitches up 10,
    facing east it rolls 10."""
    dem = flat_moon()
    yy = dem.y0 - (np.arange(dem.z.shape[0]) + 0.5) * dem.dy
    dem.z = np.tile(((yy - 20_000.0) * math.tan(math.radians(10)))[:, None], (1, dem.z.shape[1]))
    pitch, roll = rc.rover_attitude(dem, 0.0, 20_000.0, heading_deg=0)
    assert pitch == pytest.approx(10, abs=0.05) and roll == pytest.approx(0, abs=0.05)
    pitch, roll = rc.rover_attitude(dem, 0.0, 20_000.0, heading_deg=90)
    assert abs(roll) == pytest.approx(10, abs=0.05) and pitch == pytest.approx(0, abs=0.05)


def test_hill_blocks_the_dock():
    dem = rc.synthetic_crater()
    rover = (-1_000.0, 9_600.0)
    assert rc.link_angles(dem, rover, (-500.0, 7_600.0)).line_of_sight is True
    hidden = rc.link_angles(dem, rover, (3_000.0, 8_600.0))
    assert hidden.line_of_sight is False and hidden.min_clearance_m < -50


def test_geotiff_reads_same_as_memory(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin
    dem = rc.synthetic_crater()
    path = tmp_path / "crater.tif"
    with rasterio.open(path, "w", driver="GTiff", height=dem.z.shape[0], width=dem.z.shape[1], count=1,
                       dtype="float32", transform=from_origin(dem.x0, dem.y0, dem.dx, dem.dy)) as f:
        f.write(dem.z.astype("float32"), 1)
    a = rc.link_angles(dem, (-1_000.0, 9_600.0), (3_000.0, 8_600.0))
    b = rc.link_angles(rc.Dem.from_geotiff(path, bounds=(-1_000, 8_600, 3_000, 9_600)), (-1_000.0, 9_600.0), (3_000.0, 8_600.0))
    assert b.min_clearance_m == pytest.approx(a.min_clearance_m, abs=0.05)
    assert b.azimuth_deg == pytest.approx(a.azimuth_deg, abs=1e-6)
