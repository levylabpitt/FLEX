import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import igor.binarywave as ibw
from flex.db import FLEXDB

# --- Load the IBW file ---
ibw_data = ibw.load("./tests/afm_viewer/SA404950000.ibw")  # Replace with your actual file path
wave_all = ibw_data['wave']['wData']
header = ibw_data['wave']['wave_header']
note_raw = ibw_data['wave'].get('note', b'')
note = note_raw.decode('utf-8', errors='ignore')

# --- Select one layer if 3D ---
if wave_all.ndim == 3 and wave_all.shape[2] >= 1:
    wave = wave_all[:, :, 0]  # Use the first channel by default
else:
    wave = wave_all

# --- Extract image shape and scale ---
n_x = header['nDim'][0]           # number of x points
n_y = header['nDim'][1]           # number of y points
x_delta = header['sfA'][0]        # x step size
x_origin = header['sfB'][0]       # x origin
y_delta = header['sfA'][1]        # y step size
y_origin = header['sfB'][1]       # y origin

# --- Construct physical axes ---
x = x_origin + np.arange(n_x) * x_delta
y = y_origin + np.arange(n_y) * y_delta
extent = [x[0], x[-1], y[0], y[-1]]

# --- Normalize wave data to [0,1] for imshow ---
wave = wave.astype(np.float32)
wave_min = np.nanmin(wave)
wave_max = np.nanmax(wave)

if wave_max == wave_min:
    wave_norm = np.zeros_like(wave)
else:
    wave_norm = (wave - wave_min) / (wave_max - wave_min)

# --- Extract units from note ---
unit_x = unit_y = ''
for line in note.splitlines():
    if "X Units:" in line:
        unit_x = line.split(":")[1].strip()
    if "Y Units:" in line:
        unit_y = line.split(":")[1].strip()

# --- Fetch tip trace data from FLEXDB ---
START_TIME = '2025-04-16 17:00:00 -0400'
END_TIME = '2025-04-16 19:00:00 -0400'

db = FLEXDB("levylab", "llab_admin")
query = """
    SELECT time, d000, d001, d002, d003, v002
    FROM llab_079
    WHERE time BETWEEN %s AND %s
    ORDER BY time ASC
"""
rows = db.execute_fetch(query, params=(START_TIME, END_TIME), method='all')
db.close_connection()

# --- Extract trace segments from rows ---
def extract_segments(rows):
    segments = []
    current_points = []
    for row in rows:
        timestamp, x, y, speed, voltage, path_name = row
        if all(v is None for v in [speed, voltage, path_name]) and None not in (x, y):
            current_points.append((x, y+30e-6))  # Flip Y to match image orientation
        elif any(v is not None for v in [speed, voltage, path_name]):
            if current_points:
                segments.append({
                    "start_time": timestamp,
                    "speed": speed,
                    "voltage": voltage,
                    "path_name": path_name,
                    "points": current_points[::-1]  # Reverse order to match image orientation
                })
                current_points = []
    return segments

segments = extract_segments(rows)
if not segments:
    raise ValueError("No valid segments found in the specified time range.")

# --- Flatten segments into frame list ---
frames = []
for seg in segments:
    color = 'green' if seg["voltage"] and seg["voltage"] < 0 else 'red' if seg["voltage"] and seg["voltage"] > 0 else 'gray'
    for point in seg["points"]:
        frames.append((point[0], point[1], color, seg["path_name"], seg["voltage"]))

for i, seg in enumerate(segments[:3]):  # first 3 segments
    x = [pt[0] for pt in seg['points']]
    y = [pt[1] for pt in seg['points']]
    plt.figure()
    plt.plot(x, y, '-o')
    plt.title(f"Segment {i}: {seg['path_name']}")
    plt.xlabel("X")
    plt.ylabel("Y")
    plt.gca().set_aspect('equal')
    plt.show()

# --- Setup figure and animation elements ---
fig, ax = plt.subplots(figsize=(6, 5))
wave_norm = np.fliplr(np.rot90(wave_norm, k=-1))
im = ax.imshow(wave_norm, cmap='gray', origin='lower', extent=extent)
cbar = plt.colorbar(im, ax=ax, label='Normalized Height')

trace_line, = ax.plot([], [], lw=1.5, alpha=0.9, color='lime')
tip_dot = ax.scatter([], [], s=80, color='red')
tip_label = ax.text(0.02, 0.95, '', transform=ax.transAxes)
segment_label = ax.text(0.02, 0.90, '', transform=ax.transAxes)

ax.set_title("AFM Image with Animated Tip Trace")
ax.set_xlabel(f"X [{unit_x}]" if unit_x else "X (arb. units)")
ax.set_ylabel(f"Y [{unit_y}]" if unit_y else "Y (arb. units)")

trace_lines = []  # list of Line2D objects, one per segment
x_segments = [[]]  # list of x points for each segment
y_segments = [[]]  # list of y points for each segment
colors = []



# --- Animation functions ---
xdata, ydata = [], []
current_path = [None]

def init():
    for line in trace_lines:
        line.remove()
    trace_lines.clear()
    x_segments.clear()
    y_segments.clear()
    x_segments.append([])
    y_segments.append([])
    colors.clear()
    tip_dot.set_offsets(np.empty((0, 2)))
    tip_label.set_text("")
    segment_label.set_text("")
    return trace_lines + [tip_dot, tip_label, segment_label]


def update(frame):
    x, y, color, path, voltage = frame

    if path != current_path[0]:
        current_path[0] = path
        x_segments.append([])  # new segment
        y_segments.append([])
        colors.append(color)
        trace_lines.append(ax.plot([], [], lw=1.5, alpha=0.9, color=color)[0])

    if not trace_lines:
        trace_lines.append(ax.plot([], [], lw=1.5, alpha=0.9, color=color)[0])
        colors.append(color)

    x_segments[-1].append(x)
    y_segments[-1].append(y)
    trace_lines[-1].set_data(x_segments[-1], y_segments[-1])

    tip_dot.set_offsets([[x, y]])
    tip_label.set_text(f"Voltage: {voltage:.3f} V" if voltage is not None else "")
    segment_label.set_text(f"Path: {path}" if path else "")

    return trace_lines + [tip_dot, tip_label, segment_label]


ani = animation.FuncAnimation(
    fig, update, frames=frames, init_func=init,
    interval=10, blit=True, repeat=False
)

plt.tight_layout()
plt.show()
