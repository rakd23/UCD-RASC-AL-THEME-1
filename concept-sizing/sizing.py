"""
sizing.py - first-order sizing of the tethered crater explorer (RASC-AL 2027 Theme 1).

Deploy Rover (DR) on the sunlit rim  ->  tether down the wall  ->  Dock on the floor  <->  Explore Rover (ER)

Site numbers come from ../lunar-hazard-map/results/m4_summary.json ("design_inputs") when
notebook 04 has been run; otherwise the Shackleton values below are used. Every other input is
an engineering assumption in ASSUME: change one and re-run to see the whole design move.

Run:  python sizing.py            (prints a report, writes results.json next to this file)
"""
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
M4 = HERE.parent / "lunar-hazard-map" / "results" / "m4_summary.json"
g = 1.62  # m/s^2, lunar gravity

# ---------------------------------------------------------------------------
# Site: measured at Shackleton (notebook 04). Defaults = the Nov 2026 M4 run.
# ---------------------------------------------------------------------------
SITE = dict(route_km=9.36, map_length_km=8.18, drop_km=4.36, max_slope=41.2, shadow_frac=0.686,
            floor_diam_km=6.09, floor_area_km2=29.1, floor_drivable=0.847,
            floor_run_km=None, floor_in_reach_frac=None)
SITE_SOURCE = "built-in Shackleton values (Nov 2026 M4 run)"
if M4.exists():
    di = json.loads(M4.read_text()).get("design_inputs")
    if di:
        SITE.update(di)
        SITE_SOURCE = f"measured, {M4.relative_to(HERE.parent)}"

# ---------------------------------------------------------------------------
# Assumptions (placeholders for the team to replace)
# ---------------------------------------------------------------------------
ASSUME = dict(
    # tether
    slack=0.10,               # extra length for route wiggles
    floor_run_km=3.0,         # tether across the floor to the Dock, used only if notebook 04 hasn't measured it
    rho_al_293=2.82e-8,       # ohm m, aluminium at room temperature
    rho_al_cold_factor=0.30,  # resistance in shadow (77-100 K) relative to room temperature
    rho_al_hot_factor=1.22,   # resistance in sunlit stretches (~350 K)
    min_cond_mm2=0.35,        # thinnest conductor we'd handle
    insul_mm=0.10, insul_rho=1420,                 # polyimide insulation
    vectran_sigma=3.0e9, braid_eff=0.5, vectran_rho=1400, SF=5.0,   # strength member
    jacket_mm=0.30, jacket_rho=1440,               # aramid abrasion jacket
    tether_loss=0.10,         # allowed power loss in the tether
    friction_on_slope=0.3,    # tether/wheel resistance factor when climbing
    # Explore Rover
    crr=0.15, eta_drive=0.5,  # rolling resistance, drive-train efficiency
    er_batt_kwh=2.4, dod=0.8, reserve=0.20, worst_terrain=1.3,
    er_hotel_w=80.0,          # non-driving power: computer, lidar, lights, payload, heaters
    er_hotel_rhu_w=60.0,      # same, with ~20 radioisotope heater units
    dock_charge_w=150.0, charge_eff=0.9,
    transect_spacing_m=250.0, productive_frac=0.5,
    # Deploy Rover
    dr_hotel_w=70.0, dr_survival_w=35.0, dark_spell_h=120.0, batt_wh_per_kg=150.0,
    solar_w_per_m2=1361 * 0.30 * 0.75,  # sunlight x cell efficiency x losses
    array_m2=1.5,
    tether_delivered_w=100.0, tether_volts=1000.0,
    # cost
    delivery_musd_per_kg=(0.6, 0.9), dev_musd=(550, 800), ops_musd=(50, 80), reserve_frac=0.30,
)
A = ASSUME

# ER mass list: (item, current estimate kg, growth allowance)
ER_ITEMS = [("Structure + warm box", 12, .25), ("Mobility: 4 wheels, drive + steer, cold-rated", 14, .25),
            ("Avionics: rad-tolerant computer, IMU", 5, .15), ("Perception: lidar, stereo cams, LED lights", 6, .20),
            ("Battery 2.4 kWh + power electronics", 19, .15), ("Thermal: MLI, heaters, straps", 6, .30),
            ("Radio (UHF/S-band) + antenna", 3, .15), ("Harness", 4, .30),
            ("Spool, level-wind, capstan, tether brake", 12, .30), ("Dock connector (ER side)", 2, .30),
            ("Neutron spectrometer", 4, .15), ("Ground-penetrating radar", 3, .20), ("NIR spectrometer + lamp", 3.5, .20)]
DOCK_ITEMS = [("Structure + anchor feet", 5, .25), ("Battery buffer 1.0 kWh + HV DC-DC", 10, .20),
              ("Charge connector (dock side)", 3, .30), ("Radio relay + beacon", 2, .15), ("Thermal", 2, .30)]


def with_growth(items):
    return sum(m * (1 + c) for _, m, c in items)


# ---------------------------------------------------------------------------
# 1. Tether: how thick must the wires be, and what does it weigh?
# ---------------------------------------------------------------------------
def tether(P_del, V, length_km, max_tension_N):
    L = length_km * 1e3
    I = P_del / V                                          # current, A
    R_loop = A["tether_loss"] * P_del / I**2               # allowed resistance, out and back
    temp = (1 - SITE["shadow_frac"]) * A["rho_al_hot_factor"] + SITE["shadow_frac"] * A["rho_al_cold_factor"]
    A_cond = max(A["rho_al_293"] * temp * 2 * L / R_loop, A["min_cond_mm2"] * 1e-6)   # m^2 per conductor
    d_cond = math.sqrt(4 * A_cond / math.pi)
    d_ins = d_cond + 2 * A["insul_mm"] * 1e-3
    m_cond = 2 * A_cond * 2700
    m_ins = 2 * (math.pi / 4) * (d_ins**2 - d_cond**2) * A["insul_rho"]
    A_str = A["SF"] * max_tension_N / (A["vectran_sigma"] * A["braid_eff"])
    m_str = A_str * A["vectran_rho"]
    core_d = 2 * d_ins + math.sqrt(4 * A_str / math.pi)
    D = core_d + 2 * A["jacket_mm"] * 1e-3
    m_jacket = (math.pi / 4) * (D**2 - core_d**2) * A["jacket_rho"]
    lin = m_cond + m_ins + m_str + m_jacket                # kg per metre
    return dict(P_del=P_del, V=V, I_A=round(I, 3), A_cond_mm2=round(A_cond * 1e6, 2), diam_mm=round(D * 1e3, 2),
                g_per_m=round(lin * 1e3, 2), mass_kg=round(lin * L, 1), spool_L=round((math.pi / 4) * D**2 * L / 0.6 * 1e3, 1))


def sized_tether(P, V, length_km, er_mass):
    """Worst pull = ER + a full spool on the steepest pitch; tether mass and pull depend on each other, so iterate."""
    m_t, th = 80.0, math.radians(SITE["max_slope"])
    for _ in range(10):
        T = (er_mass + m_t) * g * (math.sin(th) + A["friction_on_slope"] * math.cos(th))
        t = tether(P, V, length_km, T)
        m_t = t["mass_kg"]
    t["max_tension_N"] = round(T)
    return t


# ---------------------------------------------------------------------------
# 2. Explore Rover range (the range equation)
#    r_max = E (1 - R) / (2 w (c + h / v))
# ---------------------------------------------------------------------------
def er_range(v, hotel_w, m):
    E = A["er_batt_kwh"] * 3.6e6 * A["dod"]          # usable battery, J
    c = A["crr"] * m * g / A["eta_drive"]            # driving energy per metre, J/m
    h = hotel_w / v                                  # non-driving energy per metre, J/m
    drive_per_charge = E * (1 - A["reserve"]) / (A["worst_terrain"] * (c + h))
    return drive_per_charge / 2, drive_per_charge, h / (c + h)


def straight_line_coverage(r, floor_run_km):
    """Fallback when notebook 04 hasn't run: share of a round floor within straight-line distance r of the Dock."""
    rnd = random.Random(1)
    R = SITE["floor_diam_km"] * 1e3 / 2
    dock_x = R - floor_run_km * 1e3
    n = hit = 0
    while n < 200_000:
        x, y = rnd.uniform(-R, R), rnd.uniform(-R, R)
        if x * x + y * y > R * R:
            continue
        n += 1
        hit += (x - dock_x) ** 2 + y**2 <= r * r
    return hit / n


def main():
    out = {"site_source": SITE_SOURCE, "site": SITE}
    er_mass = with_growth(ER_ITEMS)
    floor_run = SITE["floor_run_km"] if SITE.get("floor_run_km") else A["floor_run_km"]
    L_teth = (SITE["route_km"] + floor_run) * (1 + A["slack"])
    out["tether_length_km"] = round(L_teth, 2)

    trade = [sized_tether(P, V, L_teth, er_mass) for V in (300, 600, 1000) for P in (100, 150, 200)]
    base = next(t for t in trade if t["V"] == A["tether_volts"] and t["P_del"] == A["tether_delivered_w"])
    out["tether_trade"], out["tether_baseline"] = trade, base

    m_avg = er_mass + base["mass_kg"] / 2               # on the climb out the spool fills up
    E_climb = m_avg * g * (SITE["drop_km"] * 1e3 + A["crr"] * SITE["route_km"] * 1e3)
    out["climb_out_Wh"] = round(E_climb / A["eta_drive"] / 3600)

    rng = []
    for v in (0.05, 0.10, 0.15, 0.20):
        for case, hotel in (("heaters", A["er_hotel_w"]), ("heater units", A["er_hotel_rhu_w"])):
            r, dpc, share = er_range(v, hotel, er_mass)
            rng.append(dict(v=v, case=case, reach_m=round(r), drive_per_charge_m=round(dpc), non_driving_share=round(share, 2)))
    out["er_range"] = rng

    r, dpc, share = er_range(0.10, A["er_hotel_w"], er_mass)
    measured = SITE.get("floor_in_reach_frac")
    if measured:
        cover = measured.get("baseline (0.10 m/s)")
        cover_source = "measured by driving distance (notebook 04)"
    else:
        cover = straight_line_coverage(r, floor_run)
        cover_source = "straight-line estimate (run notebook 04 for the measured value)"
    # measured coverage already counts only drivable floor; the straight-line estimate doesn't
    area_km2 = SITE["floor_area_km2"] * cover if measured else SITE["floor_area_km2"] * SITE["floor_drivable"] * cover
    transect_km = area_km2 * 1e6 / A["transect_spacing_m"] / 1e3
    sortie_h = dpc / 0.10 / 3600
    used_wh = A["er_batt_kwh"] * 1e3 * A["dod"] * (1 - A["reserve"])
    charge_h = used_wh / (A["dock_charge_w"] * A["charge_eff"])
    cycles = transect_km / (dpc / 1e3 * A["productive_frac"])
    out["floor_campaign"] = dict(reach_m=round(r), floor_in_reach_pct=round(100 * cover), coverage_source=cover_source,
                                 transect_km=round(transect_km), sortie_h=round(sortie_h, 1), charge_h=round(charge_h, 1),
                                 sorties=round(cycles), floor_days=round(cycles * (sortie_h + charge_h) / 24),
                                 tether_Wh_per_cycle=round(A["tether_delivered_w"] * (sortie_h + charge_h)),
                                 er_needs_Wh_per_cycle=round(used_wh / A["charge_eff"] + 10 * (sortie_h + charge_h)))

    tether_in = A["tether_delivered_w"] / (1 - A["tether_loss"])
    batt_kwh = A["dr_survival_w"] * A["dark_spell_h"] / 1e3 / 0.8
    array_need = tether_in + A["dr_hotel_w"] + batt_kwh * 1e3 * 0.8 / (10 * 24)
    out["deploy_rover"] = dict(tether_input_W=round(tether_in), array_need_W=round(array_need),
                               array_W=round(A["array_m2"] * A["solar_w_per_m2"]),
                               battery_kWh=round(batt_kwh, 1), battery_kg=round(batt_kwh * 1e3 / A["batt_wh_per_kg"]))

    dr_items = [("Structure + ER cradle", 55, .25), ("Mobility: 4 wheels, drive + steer", 45, .25),
                ("Avionics + DTE radio + HGA", 22, .20), ("Solar array 1.5 m2 on 4 m mast + gimbal", 20, .25),
                (f"Battery {batt_kwh:.1f} kWh", batt_kwh * 1e3 / A["batt_wh_per_kg"], .15),
                ("Power electronics incl. HV supply", 8, .20), ("Thermal", 12, .30),
                ("Anchor + backup winch + tether interface", 22, .30), ("Navigation cams + lidar", 6, .20), ("Harness", 12, .30)]
    groups = {"Deploy Rover": dr_items, "Tether": [(f"Tether, {L_teth:.1f} km", base["mass_kg"], .20)],
              "Explore Rover": ER_ITEMS, "Dock": DOCK_ITEMS}
    mass = {k: dict(current_kg=round(sum(m for _, m, _ in v), 1), with_growth_kg=round(with_growth(v), 1)) for k, v in groups.items()}
    tot = sum(v["with_growth_kg"] for v in mass.values())
    mass["TOTAL"] = dict(current_kg=round(sum(v["current_kg"] for v in mass.values())), with_growth_kg=round(tot),
                         with_15pct_system_margin=round(tot * 1.15))
    out["mass"] = mass

    landed = tot * 1.15
    lo = (A["dev_musd"][0] + landed * A["delivery_musd_per_kg"][0] + A["ops_musd"][0]) * (1 + A["reserve_frac"])
    hi = (A["dev_musd"][1] + landed * A["delivery_musd_per_kg"][1] + A["ops_musd"][1]) * (1 + A["reserve_frac"])
    out["cost_musd"] = dict(low=round(lo), high=round(hi),
                            delivery_low=round(landed * A["delivery_musd_per_kg"][0]),
                            delivery_high=round(landed * A["delivery_musd_per_kg"][1]))
    (HERE / "results.json").write_text(json.dumps(out, indent=1))
    report(out)


def report(o):
    f, t, c, d, m = o["floor_campaign"], o["tether_baseline"], o["cost_musd"], o["deploy_rover"], o["mass"]
    print(f"Site numbers: {o['site_source']}")
    print(f"\nTETHER  {o['tether_length_km']} km at {t['V']:.0f} V, {t['P_del']:.0f} W delivered")
    print(f"  {t['diam_mm']} mm thick, {t['g_per_m']} g/m, {t['mass_kg']} kg, ~{t['spool_L']:.0f} L on the drum; worst pull {t['max_tension_N']} N")
    print("  mass (kg) by voltage / power:")
    for V in (300, 600, 1000):
        row = [x["mass_kg"] for x in o["tether_trade"] if x["V"] == V]
        print(f"    {V:>4} V: " + "  ".join(f"{p} W = {mm:>6.0f}" for p, mm in zip((100, 150, 200), row)))
    print(f"\nEXPLORE ROVER  reach {f['reach_m']} m from the Dock at 0.10 m/s; "
          f"{100 * o['er_range'][2]['non_driving_share']:.0f}% of energy is non-driving")
    for x in o["er_range"]:
        print(f"    {x['v']:.2f} m/s, {x['case']:<12} reach {x['reach_m']:>5} m")
    print(f"  floor in reach {f['floor_in_reach_pct']}% ({f['coverage_source']})")
    print(f"  {f['transect_km']} km of transects = {f['sorties']} sorties x ({f['sortie_h']} h out + {f['charge_h']} h charging) "
          f"= ~{f['floor_days']} days")
    print(f"  climb out: ~{o['climb_out_Wh']} Wh, drawn through the live tether")
    print(f"\nDEPLOY ROVER  needs {d['array_need_W']} W, array gives {d['array_W']} W; battery {d['battery_kWh']} kWh ({d['battery_kg']} kg)")
    print("\nMASS (kg)       current  with growth")
    for k, v in m.items():
        if k != "TOTAL":
            print(f"  {k:<14} {v['current_kg']:>7}  {v['with_growth_kg']:>8}")
    print(f"  TOTAL          {m['TOTAL']['current_kg']:>7}  {m['TOTAL']['with_growth_kg']:>8}   "
          f"with 15% system margin: {m['TOTAL']['with_15pct_system_margin']}")
    print(f"\nCOST (rough)  ${c['low']:,}M - ${c['high']:,}M incl. reserve; delivery ${c['delivery_low']}-{c['delivery_high']}M")
    print("\nWrote results.json")


if __name__ == "__main__":
    main()
