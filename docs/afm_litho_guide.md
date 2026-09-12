# AFM Lithography User Guide (`afm-litho`)

This guide explains how conductive-AFM lithography works in the Levy Lab and how to control the microscope using the `AFMLitho` driver in `flex`.

---

## 1. What is AFM Lithography?

Atomic Force Microscopy (AFM) lithography uses a microscopic conductive tip to draw nanometer-scale features on a sample surface.

- **Scanning**: The tip moves across the surface in a raster pattern to image terrain or conductance.
- **Writing**: The tip engages the surface, applies a controlled voltage bias to write conductive lines or patterns, and retracts.

The system runs in two modes:
1. **Digital Twin (`backend="twin"`)**: A local software simulation for testing scripts offline without touching physical hardware.
2. **Hardware (`backend="hardware"`)**: Drives the physical Asylum AFM via Igor Pro bridge.

---

## 2. Architecture & Communication

The `afm-litho` application runs as a background service exposing **two ZeroMQ ports**:

| Port | Name | Purpose |
| --- | --- | --- |
| `29180` | **Command Port** | Executes action verbs (`start_scan`, `write`, `approach`, `acquire_control`, `heartbeat`). |
| `29181` | **Read Port** | Fast, non-blocking state and sensor queries (`get_state`, `get_deflection`, `get_sum`). |

**Why two ports?**  
Polling state on the Read Port will never stall or freeze behind a long 20-minute scan running on the Command Port.

---

## 3. Control Arbitration & Tokens

To prevent two scripts (or an operator and a script) from moving the tip simultaneously, `afm-litho` uses a **control token**:

1. Call `afm.acquire_control("script_name")` before sending any tip-moving commands.
2. Call `afm.heartbeat()` periodically (or use `afm.session()` context manager) to keep the dead-man timer active.
3. Call `afm.release_control()` when your script finishes.

---

## 4. Tip States

| State | Meaning |
| --- | --- |
| `idle` | Tip is withdrawn and safe above the surface. |
| `engaged` | Tip is lowered in contact with the surface. |
| `scanning` | Tip is performing a raster imaging scan. |
| `writing` | Tip is applying voltage to draw a lithography pattern. |
| `parked` | Tip has been retracted and parked via emergency fail-safe. |

---

## 5. Code Examples

### Standard Imaging Scan
```python
from flex.inst.levylab import AFMLitho

afm = AFMLitho("tcp://localhost:29180")

# Use session context manager to auto-acquire/release token and handle cleanup
with afm.session(client="scan_demo", deadman_s=30) as tip:
    # Lower tip to surface
    tip.approach()

    # Perform raster scan (blocking helper)
    result = tip.scan(size_um=2.0, pixels=256, lines=256)
    print("Scan completed:", result)

    # Raise tip off surface
    tip.withdraw()
```

### Pattern Writing (Nanometer SVG Lines)
```python
from flex.inst.levylab import AFMLitho

# 1 unit = 1 nanometer in inline SVG
SVG_PATTERN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-50 -50 100 100">
  <path d="M 0 0 L 20 20" stroke="black" stroke-width="1" />
</svg>"""

afm = AFMLitho("tcp://localhost:29180")

with afm.session(client="write_demo") as tip:
    # 1. Compile pattern
    tip.load_pattern(SVG_PATTERN)

    # 2. Engage tip
    tip.approach()

    # 3. Write pattern with voltage
    write_result = tip.write(objects="all")
    print("Write completed:", write_result)

    # 4. Withdraw tip
    tip.withdraw()
```

---

## 6. Complete API Reference (`AFMLitho`)

Nothing has been omitted. Here is the complete list of all methods available in the `AFMLitho` driver, categorized by feature area:

### Status & Sensor Queries (Read Socket)
| Method | Description |
| --- | --- |
| `idn()` | Returns vendor, model, serial, and active backend (`twin` or `hardware`). |
| `get_state()` | Returns current state string (`idle`, `engaged`, `scanning`, `writing`, `parked`). |
| `get_status()` | Returns status dict (commander name, backend, bridge state, safe-park status). |
| `get_telemetry()` | Returns live position & sensor values (`x_um`, `y_um`, `defl_v`, `sum_v`, `zdrive_v`). |
| `get_mode()` | Returns imaging mode (`contact`, `tapping`, `litho`). |
| `get_written()` | Returns list of object indices written in the current session. |
| `get_scan_result(run_id, inline=True)` | Returns scan metadata and image array trace. |
| `get_write_result(run_id, inline=True)` | Returns write metadata and executed tip voltage trace. |

### Control Token & Session Management
| Method | Description |
| --- | --- |
| `acquire_control(client, deadman_s=30)` | Claims control token and arms dead-man watchdog timer. |
| `release_control()` | Releases held control token. |
| `heartbeat()` | Refreshes dead-man timer on the server. |
| `require_token()` | Returns current token or raises `ControlRequired`. |
| `session(client, deadman_s=30)` | Context manager (`with afm.session(...)`) for auto token management & cleanup. |

### Emergency & Fail-Safe Functions
| Method | Description |
| --- | --- |
| `abort()` | **Token-free** emergency stop (immediately retracts tip). |
| `safe_park(reason)` | **Token-free** emergency park. |
| `abort_write()` | **Token-free** write stop; retracts tip while preserving partial trace data. |

### Scan & Motion Control
| Method | Description |
| --- | --- |
| `set_mode(mode="contact")` | Changes operating mode. |
| `start_approach(...)` | Initiates tip approach (non-blocking). |
| `approach(...)` | Lowers tip to surface (blocking convenience helper). |
| `withdraw()` | Retracts tip to safe `idle` state. |
| `set_z_gain(pgain, igain)` | Sets Z feedback loop gains. |
| `start_scan(size_um, pixels, ...)` | Initiates raster scan (non-blocking). |
| `scan(size_um, pixels, ...)` | Runs raster scan and returns final image (blocking convenience helper). |
| `set_continuous(enabled=True)` | Toggles continuous auto-repeat imaging loop. |

### Lithography Pattern Writing
| Method | Description |
| --- | --- |
| `load_pattern(source)` | Compiles and validates SVG string, SVG/GDS/OASIS file path, or design name. |
| `start_write(objects="all", ...)` | Initiates tip-bias writing (non-blocking). |
| `write(objects="all")` | Executes pattern writing and returns voltage trace (blocking convenience helper). |

### Direct Instrument Parameters
Access via `afm.parameters["<name>"].get()`:
`state`, `backend`, `x`, `y`, `deflection`, `sum`, `zdrive`.

---

## 7. Code Examples

### Standard Imaging Scan
```python
from flex.inst.levylab import AFMLitho

afm = AFMLitho("tcp://localhost:29180")

with afm.session(client="scan_demo", deadman_s=30) as tip:
    tip.approach()
    result = tip.scan(size_um=2.0, pixels=256, lines=256)
    print("Scan completed:", result)
    tip.withdraw()
```

### Pattern Writing (Nanometer SVG Lines)
```python
from flex.inst.levylab import AFMLitho

SVG_PATTERN = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="-50 -50 100 100">
  <path d="M 0 0 L 20 20" stroke="black" stroke-width="1" />
</svg>"""

afm = AFMLitho("tcp://localhost:29180")

with afm.session(client="write_demo") as tip:
    tip.load_pattern(SVG_PATTERN)
    tip.approach()
    write_result = tip.write(objects="all")
    print("Write completed:", write_result)
    tip.withdraw()
```

