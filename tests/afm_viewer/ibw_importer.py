import numpy as np
import matplotlib.pyplot as plt
import igor.binarywave as ibw

# --- Load the IBW file ---
ibw_data = ibw.load("./tests/afm_viewer/SA40656B0000.ibw")
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

# --- Plot the image ---
fig, ax = plt.subplots(figsize=(6, 5))
wave_norm = np.fliplr(np.rot90(wave_norm, k=-1))

im = ax.imshow(wave_norm, cmap='gray', origin='lower', extent=extent)
cbar = plt.colorbar(im, ax=ax, label='Normalized Height')

ax.set_title("AFM Image from IBW")
ax.set_xlabel(f"X [{unit_x}]" if unit_x else "X (arb. units)")
ax.set_ylabel(f"Y [{unit_y}]" if unit_y else "Y (arb. units)")

plt.tight_layout()
plt.show()
