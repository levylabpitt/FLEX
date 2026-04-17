import clr
import sys
import os

# Load the DLL
DLL_PATH = os.environ.get("ProgramFiles") + "\\Newport\\Piezo Motion Control\\Newport CONEX-AGP Applet\\Bin"
sys.path.append(DLL_PATH)
clr.AddReference(f"{DLL_PATH}\\ConexAGPCmdLib.DLL")

from Newport.ConexAGPCmdLib import ConexAGPCmds


class ConexAGPDriver:
    def __init__(self, port: str = 'COM8', addr: int = 1):
        self.port = port
        self.addr = addr
        self.controller = ConexAGPCmds()

        status = self.controller.OpenInstrument(self.port)
        if status != 0:
            raise ConnectionError(f"Failed to open connection to {self.port}")
        print(f"[CONNECTED] Controller on {self.port}")

    def close(self):
        status = self.controller.CloseInstrument()
        if status != 0:
            raise ConnectionError("Failed to close instrument.")
        print("[DISCONNECTED] Controller closed.")

    def get_version(self):
        raw = self.controller.VE(self.addr)
        return raw[1]

    def get_position(self):
        raw = self.controller.TP(self.addr)
        return raw[1]

    def move_absolute(self, position: float):
        status = self.controller.PA_Set(self.addr, position)
        if status[0] != 0:
            raise RuntimeError(f"PA_Set failed")
        print(f"[MOVE] Moved to absolute position {position:.4f}")

    def move_relative(self, delta: float):
        status = self.controller.PR_Set(self.addr, delta)
        if status != 0:
            raise RuntimeError(f"PR_Set failed")
        print(f"[MOVE] Moved relatively by {delta:.4f}")

    def stop(self):
        self.controller.ST(self.addr)
        print("[STOP] Motion stopped.")

    def home(self):
        err = ""
        status = self.controller.OR(self.addr, err)
        if status != 0:
            raise RuntimeError(f"Home (OR) failed: {err}")
        print("[HOME] Homing complete.")

    def get_status(self):
        error_code, state, err = "", "", ""
        self.controller.TS(self.addr, error_code, state, err)
        return dict(error_code=error_code, state=state, error=err)

    def get_all_params(self):
        params, err = [], ""
        self.controller.ZT(self.addr, params, err)
        return params, err


if __name__ == "__main__":
    # Example usage
    stage = ConexAGPDriver(port="COM8")
    version = stage.get_version()
    print(f"Controller version: {version}")

    position = stage.get_position()
    print(f"Current position: {position}")
    import time
    # stage.move_absolute(15.1)
    # stage.move_relative(-2.0)
    print(stage.get_position())

    # stage.stop()
    # stage.home()
    stage.close()
