import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from flex.db import FLEXDB

# --- Database parameters ---
START_TIME = '2025-04-18 18:00:00 -0400'
END_TIME = '2025-04-18 18:27:00 -0400'

# --- Connect to DB and fetch data ---
db = FLEXDB("levylab", "llab_admin")
query = """
    SELECT time, d000, d001, d002, d003, v002
    FROM llab_079
    WHERE time BETWEEN %s AND %s
    ORDER BY time ASC
"""
rows = db.execute_fetch(query, params=(START_TIME, END_TIME), method='all')
db.close_connection()

# --- Segment parser ---
def extract_segments(rows):
    segments = []
    current_points = []

    for row in rows:
        timestamp, x, y, speed, voltage, path_name = row

        if all(v is None for v in [speed, voltage, path_name]) and None not in (x, y):
            current_points.append((x, y))

        elif any(v is not None for v in [speed, voltage, path_name]):
            if current_points:
                segments.append({
                    "start_time": timestamp,
                    "speed": speed,
                    "voltage": voltage,
                    "path_name": path_name,
                    "points": current_points[::-1]
                })
                current_points = []

    return segments

segments = extract_segments(rows)
if not segments:
    raise ValueError("No valid segments found in the specified time range.")

# --- Animation setup ---
fig, ax = plt.subplots()
tip_dot = ax.scatter([], [], s=80)
current_trace_line, = ax.plot([], [], lw=1.5, alpha=0.9, label='Current Segment')
past_trace_lines = []  # list of Line2D objects

tip_label = ax.text(0.02, 0.95, '', transform=ax.transAxes)
segment_label = ax.text(0.02, 0.90, '', transform=ax.transAxes)

# Bounds
all_x = [x for seg in segments for x, _ in seg["points"]]
all_y = [y for seg in segments for _, y in seg["points"]]
ax.set_xlim(min(all_x), max(all_x))
ax.set_ylim(min(all_y), max(all_y))
ax.set_xlabel("X (m)")
ax.set_ylabel("Y (m)")
ax.set_title("AFM Tip Path Animation")

# Flatten into frame list
frames = []
for seg in segments:
    color = 'green' if seg["voltage"] and seg["voltage"] > 0 else 'red' if seg["voltage"] and seg["voltage"] < 0 else 'gray'
    for i, point in enumerate(seg["points"]):
        frames.append((point[0], point[1], color, seg["path_name"], seg["voltage"]))

# Trace buffer
trace_x, trace_y = [], []
current_path = [None]  # mutable tracker

def init():
    tip_dot.set_offsets(np.empty((0, 2)))
    current_trace_line.set_data([], [])
    tip_dot.set_color('gray')
    tip_label.set_text("")
    segment_label.set_text("")
    trace_x.clear()
    trace_y.clear()
    current_path[0] = None

    # Clear all previous path lines (if re-running)
    for line in past_trace_lines:
        line.remove()
    past_trace_lines.clear()

    return tip_dot, current_trace_line, tip_label, segment_label

def update(frame):
    x, y, color, path, voltage = frame

    if path != current_path[0]:
        # finalize the last trace line
        if trace_x and trace_y:
            past_line, = ax.plot(trace_x, trace_y, lw=1.2, alpha=0.5, color=color)
            past_trace_lines.append(past_line)

        trace_x.clear()
        trace_y.clear()
        current_trace_line.set_data([], [])
        current_path[0] = path

    # update current tip
    tip_dot.set_offsets([[x, y]])
    tip_dot.set_color(color)

    trace_x.append(x)
    trace_y.append(y)
    current_trace_line.set_data(trace_x, trace_y)

    tip_label.set_text(f"Voltage: {voltage:.3f} V" if voltage is not None else "")
    segment_label.set_text(f"Path: {path}" if path else "")

    return [tip_dot, current_trace_line, tip_label, segment_label] + past_trace_lines

ani = animation.FuncAnimation(
    fig, update, frames=frames, init_func=init,
    interval=50, blit=True, repeat=False
)

plt.show()