# FLEX Package Integration & Architecture Notes

This document describes the structural changes made to integrate the conductive-AFM lithography driver directly into the `flex` framework.

---

## 1. Summary of Changes

The external `flex-afm` driver repository has been integrated directly into `flex` source code.

1. **Enhanced Base ZMQ Transport (`flex/src/flex/inst/base.py`)**:
   - Added ZMQ socket recovery on timeout/error to prevent `EFSM` socket lockups.
   - Added per-call timeout capability (`_send_command(cmd, params, timeout=...)`).
   - Added monotonic request IDs (`1`, `2`, `3`...) instead of integer timestamps.
   - Added generic `ZMQInstrumentError` exception class.
   - Added optional `Parameter` class and `add_parameter()` handle registration.

2. **Native AFM Litho Driver (`flex/src/flex/inst/levylab/afm_litho.py`)**:
   - Created `AFMLitho` inheriting directly from `Instrument` in `flex.inst.base`.
   - Defined AFM-specific exceptions (`ControlHeld`, `ControlRevoked`, `ControlRequired`, `BackendMismatch`, `Busy`, `Refused`, `PatternTooLarge`).
   - Managed command socket (`port`) and read socket (`port + 1`) internally.

3. **Package Export (`flex/src/flex/inst/levylab/__init__.py`)**:
   - Exported `AFMLitho` so scripts can import directly via:
     ```python
     from flex.inst.levylab import AFMLitho
     ```

4. **Optional Station Loader (`flex/src/flex/station.py`)**:
   - Added standalone `Station.load("flex.toml")` utility for users who want `.toml` configuration loading.

---

## 2. Backwards Compatibility

All changes to `flex/src/flex/inst/base.py` are strictly backwards-compatible with all existing FLEX instrument drivers (`Lockin`, `Krohn_Hite_7008`, `Aerotech`, `Cryostation`, `PPMS`, etc.).

- Existing instrument constructors (`Lockin(address, log_file=...)`) continue to work without modification.
- Existing method calls (`lockin.getAO(...)`, `lockin.setAO_Amplitude(...)`) remain identical.
- `Parameter` registration is opt-in and does not interfere with existing drivers.

---

## 3. Directory Structure

```
flex/
├── docs/
│   ├── afm_litho_guide.md            # AFM Lithography user guide
│   └── flex_afm_integration.md       # Integration technical notes (this file)
└── src/
    └── flex/
        ├── station.py                # Optional flex.toml station loader
        └── inst/
            ├── base.py               # Base ZMQ Instrument (enhanced)
            └── levylab/
                ├── __init__.py       # Exports AFMLitho, Lockin, Krohn_Hite_7008
                └── afm_litho.py      # Core AFMLitho driver
```
