import math

MOON_RADIUS = 1_737_400  # meters


def comm_angle(rover, target, terrain):
    """
    rover, target: (x, y, height) in meters, antenna height included
    terrain: ground heights in meters, sampled evenly along the line from rover to target
    """
    dx = target[0] - rover[0]
    dy = target[1] - rover[1]
    dz = target[2] - rover[2]

    # Step 1: flat distance along the ground
    distance = math.sqrt(dx**2 + dy**2)

    # Step 2: azimuth = which way to turn the antenna (0 = north, 90 = east)
    azimuth = math.degrees(math.atan2(dx, dy)) % 360

    # Step 3: elevation = how far to tilt the antenna up.
    # The Moon curves away, so the target sits a little lower than it looks.
    curve_drop = distance**2 / (2 * MOON_RADIUS)
    elevation = math.degrees(math.atan2(dz - curve_drop, distance))

    # Step 4: line of sight. Walk along the beam and check the ground never pokes above it.
    n = len(terrain)
    clear = True
    for i in range(1, n - 1):
        t = i / (n - 1)                                   # fraction of the way to the target
        beam = rover[2] + t * dz                          # beam height at this point
        d1, d2 = t * distance, (1 - t) * distance
        bulge = d1 * d2 / (2 * MOON_RADIUS)               # Moon's curvature lifts the ground
        if terrain[i] + bulge >= beam:
            clear = False
            break

    return azimuth, elevation, clear


# ---- Example: scout on the crater floor talking to a tower on the rim ----
rover = (0, 0, -4000 + 0.5)          # floor at -4000 m, 0.5 m antenna
tower = (2000, 11500, 200 + 30)      # rim at +200 m, 30 m tower
terrain = [-4000] * 40 + [-4000 + 100 * i for i in range(43)]   # flat floor, then wall up to the rim

az, el, clear = comm_angle(rover, tower, terrain)
print(f"Point antenna: azimuth {az:.1f} deg, elevation {el:.1f} deg")
print("Line of sight:", "CLEAR" if clear else "BLOCKED")
