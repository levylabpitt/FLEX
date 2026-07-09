# Deferred v1 drivers

These v1 drivers were **not** ported to `flex-drivers` because they depend on
Windows-only binary runtimes (vendor DLLs, .NET, or COM) rather than a portable
transport (pyvisa / pyserial / sockets). They need either a vendor SDK wrapper
package or a rewrite against the underlying wire protocol before they can join
this package.

| v1 source | Class | Reason deferred | What it needs |
| --- | --- | --- | --- |
| `src/flex/inst/newport/ConexAGP.py` | `ConexAGPDriver` | Uses pythonnet (`clr`) to load the Newport `ConexAGPCmdLib.DLL` .NET assembly from `%ProgramFiles%\Newport\Piezo Motion Control\...`. | pythonnet + installed Newport CONEX-AGP applet, or a rewrite against the CONEX serial command set (the controller is fundamentally an RS-232 device, so a future `SerialInstrument` port is feasible). |
| `src/flex/inst/newport/NF8742.py` | `NF8742` | Uses pythonnet (`clr`) to load New Focus `UsbDllWrap` (.NET `Newport.USBComm.USB`, `System.Text.StringBuilder`) from `%ProgramFiles%\New Focus\...`. | pythonnet + New Focus Picomotor application, or a rewrite using the 8742's documented USB/Ethernet SCPI-like protocol (e.g. via TCP port 23). |
| `src/flex/inst/ophir/OphirNova.py` | `OphirNova2` | Uses pywin32 COM (`win32com.client.Dispatch("OphirLMMeasurement.CoLMMeasurement")`, plus `win32gui`). | pywin32 + the Ophir StarLab / OphirLMMeasurement COM component installed on Windows. |
| `src/flex/inst/sphere/DScan.py` | `DScan` | Loads the proprietary `dscan-library.dll` via `ctypes` from `%ProgramFiles%\Sphere Ultrafast Photonics S.A\dscan-library\bin` — and does so at *import* time (module-level `LoadLibrary`), which v2 forbids. | The vendor DLL (Windows-only) and a lazy-loading ctypes wrapper, or a documented wire protocol. |
