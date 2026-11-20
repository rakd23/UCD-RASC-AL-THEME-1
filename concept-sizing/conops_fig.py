"""
conops_fig.py - draws the concept-of-operations cross-section (figures/conops.png).
Reads site and design numbers from results.json, so run sizing.py first.
"""
import json
from pathlib import Path
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Polygon, Rectangle

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results.json").read_text())
S, TB, FC = R["site"], R["tether_baseline"], R["floor_campaign"]
MAPLEN, DROP = S.get("map_length_km", 8.18), S["drop_km"]
FLOOR_W = S["floor_diam_km"]
RUN = S["floor_run_km"] if S.get("floor_run_km") else 3.0
REACH = FC["reach_m"] / 1000

plt.rcParams['font.family'] = 'DejaVu Sans'
INK, MUTED, RULE = '#1f2328', '#5b6470', '#c9ced6'
BLUE, AMBER, SHADOW, SUN = '#2b6cb0', '#c47f17', '#e9ecf2', '#f2c14e'

fig, ax = plt.subplots(figsize=(13, 6.2), dpi=200)

# --- terrain profile (true scale, km): route map length and drop from notebook 04 ---
x_rim = np.linspace(-3.2, 0, 50); y_rim = np.zeros_like(x_rim)
xw = np.linspace(0, MAPLEN, 300)
t = xw / MAPLEN
yw = -DROP * (np.sin(t * np.pi / 2) ** 1.6)  # schematic shape: steep upper wall, easing at the foot
XEND = MAPLEN + FLOOR_W
x_floor = np.linspace(MAPLEN, XEND, 60); y_floor = np.full_like(x_floor, -DROP)
X = np.concatenate([x_rim, xw, x_floor]); Y = np.concatenate([y_rim, yw, y_floor])
ax.fill_between(X, Y, -DROP - 0.85, color='#d8dbe1', zorder=1)
ax.plot(X, Y, color=INK, lw=1.6, zorder=3)

# permanent shadow: tint the crater interior beyond the shadow line; mark shadowed ground with a dark band
shadow_start = (1 - S['shadow_frac']) * MAPLEN   # shadowed share of the route (notebook 04)
xs = np.concatenate([xw[xw >= shadow_start], x_floor]); ys = np.concatenate([yw[xw >= shadow_start], y_floor])
ax.fill_between(xs, ys, 0, color='#eef1f6', zorder=0.5)
ax.plot(xs, ys - 0.07, color='#6b7380', lw=3.2, zorder=2.5, solid_capstyle='butt')
ax.text(MAPLEN + FLOOR_W / 2, -1.05, 'permanently shadowed interior (floor ~25-40 K)', ha='center', fontsize=9, color=MUTED, style='italic', zorder=4)
# sun ray
ax.annotate('', xy=(-1.05, 0.62), xytext=(-3.3, 0.66), arrowprops=dict(arrowstyle='->', color=SUN, lw=2.2))
ax.text(-3.3, 0.82, 'low Sun, near the horizon', fontsize=8.5, color='#9a7412')

# tether along route (offset slightly above ground) to the dock 3 km onto the floor
dock_x = MAPLEN + RUN
tx = np.concatenate([np.linspace(-0.45, 0, 10), xw, np.linspace(MAPLEN, dock_x, 30)])
ty = np.concatenate([np.full(10, 0.0), yw, np.full(30, -DROP)]) + 0.06
ax.plot(tx, ty, color=BLUE, lw=2.0, zorder=5)

def rover(x, y, w, h, color, label=None, mast=False):
    ax.add_patch(FancyBboxPatch((x - w / 2, y + 0.05), w, h, boxstyle='round,pad=0.01,rounding_size=0.03',
                                facecolor='white', edgecolor=color, lw=1.6, zorder=7))
    for dx in (-w / 3, w / 3):
        ax.add_patch(Circle((x + dx, y + 0.05), h * 0.32, facecolor='white', edgecolor=color, lw=1.4, zorder=8))
    if mast:
        ax.plot([x, x], [y + 0.05 + h, y + 0.05 + h + 0.55], color=color, lw=1.4, zorder=7)
        ax.add_patch(Rectangle((x - 0.07, y + h + 0.32), 0.14, 0.36, facecolor=SUN, edgecolor=color, lw=1, zorder=8))
    if label:
        ax.text(x, y + 0.05 + h / 2, label, ha='center', va='center', fontsize=8, color=color, weight='bold', zorder=9)

# DR at rim with solar mast
rover(-0.9, 0, 0.9, 0.28, INK, 'DR', mast=True)
# ER on the wall (descending) and on the floor
xe = 3.6; ye = np.interp(xe, xw, yw)
rover(xe, ye, 0.5, 0.18, BLUE, 'ER')
# dock
ax.add_patch(Rectangle((dock_x - 0.15, -DROP), 0.3, 0.2, facecolor=BLUE, edgecolor=INK, lw=1, zorder=8))
ax.text(dock_x, -DROP - 0.26, 'Dock', ha='center', fontsize=8.5, color=BLUE, weight='bold')
# sortie radius bar
r = REACH
ax.annotate('', xy=(max(dock_x - r, MAPLEN), -DROP - 0.49), xytext=(min(dock_x + r, XEND), -DROP - 0.49),
            arrowprops=dict(arrowstyle='<->', color=AMBER, lw=1.5))
ax.text(dock_x, -DROP - 0.69, f'ER reach ≈ {REACH:.1f} km by driving (0.1 m/s, battery only)', ha='center', fontsize=8.5, color='#8a5a0f')
rover(dock_x + 1.4, -DROP, 0.5, 0.18, BLUE, 'ER')
ax.annotate('', xy=(dock_x + 2.1, -4.0), xytext=(dock_x + 1.6, -4.0), arrowprops=dict(arrowstyle='->', color=BLUE, lw=1.2))

# numbered steps
def step(n, x, y, txt, ha='left'):
    ax.add_patch(Circle((x, y), 0.17, facecolor=INK, edgecolor='none', zorder=10))
    ax.text(x, y, str(n), color='white', ha='center', va='center', fontsize=8.5, weight='bold', zorder=11)
    ax.text(x + (0.28 if ha == 'left' else -0.28), y, txt, ha=ha, va='center', fontsize=8.6, color=INK, zorder=11, bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor='none', alpha=0.9))

step(1, -2.9, -0.55, 'Lands on lit rim;\nDR carries ER')
step(5, -2.9, -1.25, 'DR solar mast + battery\nfeeds tether 24/7')
step(2, 3.2, -1.0, 'ER rappels, paying tether out\nfrom its own spool; DR anchors')
step(3, MAPLEN + 0.4, -2.35, f'ER sets Dock ~{RUN:.1f} km\nonto the floor')
step(4, dock_x, -3.25, 'Sorties: map, return,\ncharge, upload')
step(6, 0.6, -2.55, 'ER re-connects\nto the tether end')
step(7, 0.6, -3.25, 'ER reels itself up its own\npath; DR winch = backup')
step(8, -2.9, -1.95, 'DR drives ER along the lit\nridge to the next crater')
ax.annotate('', xy=(-3.3, 0.3), xytext=(-1.5, 0.3), arrowprops=dict(arrowstyle='->', color=INK, lw=1.2, ls='--'))

ax.plot([MAPLEN + 0.4, MAPLEN + 1.0], [-0.62, -0.62], color='#6b7380', lw=3.2)
ax.text(MAPLEN + 1.1, -0.62, f"ground in permanent shadow ({100 * S['shadow_frac']:.0f}% of route)", va='center', fontsize=8.3, color=MUTED)
ax.plot([MAPLEN + 0.4, MAPLEN + 1.0], [-0.35, -0.35], color=BLUE, lw=2)
ax.text(MAPLEN + 1.1, -0.35, 'tether: power + data', va='center', fontsize=8.3, color=MUTED)
# key numbers box
box = (f"Shackleton, measured from LOLA 5 m (notebook 04)\n"
       f"Route rim → floor: {S['route_km']:.1f} km on the ground, {DROP:.2f} km drop\n"
       f"Steepest point {S['max_slope']:.0f}°  ·  {100 * S['shadow_frac']:.0f}% of route in permanent shadow\n"
       f"Floor ≈ {FLOOR_W:.1f} km across\n"
       f"Tether: {R['tether_length_km']:.1f} km, {TB['V']:.0f} V DC, {TB['P_del']:.0f} W delivered, ~{TB['mass_kg']:.0f} kg")
ax.text(XEND - 0.05, 1.15, box, ha='right', va='top', fontsize=8.6, color=INK,
        bbox=dict(boxstyle='round,pad=0.5', facecolor='white', edgecolor=RULE))

ax.set_xlim(-3.4, XEND + 0.1); ax.set_ylim(-DROP - 0.9, 1.3)
ax.set_aspect('equal')
ax.set_xlabel('distance from Deploy Rover (km)', fontsize=9, color=MUTED)
ax.set_ylabel('height relative to rim (km)', fontsize=9, color=MUTED)
for s in ('top', 'right'): ax.spines[s].set_visible(False)
for s in ('left', 'bottom'): ax.spines[s].set_color(RULE)
ax.tick_params(colors=MUTED, labelsize=8)
ax.set_title('Tethered crater explorer: one Deploy Rover, one Explore Rover, one tether, reused crater to crater',
             fontsize=11.5, color=INK, loc='left', pad=10)
fig.text(0.01, 0.01, 'True vertical scale. Wall shape is schematic; route length, drop, slope and shadow figures are measured. Sizes of vehicles not to scale.',
         fontsize=7.5, color=MUTED)
plt.tight_layout()
(HERE / 'figures').mkdir(exist_ok=True)
plt.savefig(HERE / 'figures' / 'conops.png', dpi=200)
print('Wrote figures/conops.png')
