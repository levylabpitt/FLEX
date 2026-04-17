import os
import sys
import clr # install pythonnet instead of clr
import time

# Load the vendor DLL
DLL_PATH = os.environ.get("ProgramFiles") + "\\New Focus\\New Focus Picomotor Application\\Bin"
sys.path.append(DLL_PATH)
clr.AddReference("UsbDllWrap")

from Newport.USBComm import USB
from System.Text import StringBuilder

class NF8742:
    def __init__(self, axis: int):
        if axis not in [1, 2, 3, 4]:
            raise ValueError("Axis must be 1, 2, 3, or 4")
        self.axis = axis
        self.usb = USB(True)
        self.device_key = None
        self.connected = False
        self._connect_to_device()

    def _connect_to_device(self):
        if self.usb.OpenDevices(0, True):
            device_table = self.usb.GetDeviceTable()
            if device_table.Count == 0:
                raise RuntimeError("No devices found.")
            enumerator = device_table.GetEnumerator()
            if enumerator.MoveNext():
                self.device_key = str(enumerator.Key)
                self.connected = True
        else:
            raise RuntimeError("Could not open USB devices.")

    def _query(self, command: str):
        buf = StringBuilder(128)
        status = self.usb.Query(self.device_key, command, buf)
        return status, buf.ToString()

    def close(self):
        self.usb.CloseDevices()
        self.connected = False

    # === Public Commands (axis is fixed on init) ===

    def get_idn(self):
        return self._query("*IDN?")[1]

    def reset(self):
        return self._query("*RST")

    def get_position(self):
        return self._query(f"{self.axis}TP?")[1]

    def move_absolute(self, position: int):
        return self._query(f"{self.axis}PA{position}")

    def move_relative(self, steps: int):
        return self._query(f"{self.axis}PR{steps}")

    def move_direction(self, direction: int):
        return self._query(f"{self.axis}MV{direction}")  # 1 = forward, 0 = reverse

    def stop(self):
        return self._query(f"{self.axis}ST")

    def abort(self):
        return self._query(f"{self.axis}AB")

    def get_velocity(self):
        return self._query(f"{self.axis}VA?")[1]

    def set_velocity(self, value: int):
        return self._query(f"{self.axis}VA{value}")

    def get_destination(self):
        return self._query(f"{self.axis}PA?")[1]

    def is_motion_done(self):
        return self._query(f"{self.axis}MD?")[1] == '1'

    def get_direction(self):
        return self._query(f"{self.axis}MV?")[1]

    def get_error_text(self):
        return self._query("TB?")[1]

    def get_error_number(self):
        return self._query("TE?")[1]

    def get_motor_type(self):
        return self._query("QM?")[1]

    def get_motor_type_extended(self):
        return self._query("QM7?")[1]

    def get_config_register(self):
        return self._query("ZZ?")[1]

    def purge(self):
        return self._query("XX")

    def move_and_wait_absolute(self, position: int, poll_interval: float = 0.1):
        """Move to an absolute position and wait until the move completes."""
        self.move_absolute(position)
        print(f"[Axis {self.axis}] Moving to position {position}...")
        while not self.is_motion_done():
            time.sleep(poll_interval)
        return self.get_position()

    def move_and_wait_relative(self, steps: int, poll_interval: float = 0.1):
        """Move relatively and wait until the move completes."""
        self.move_relative(steps)
        print(f"[Axis {self.axis}] Moving relative by {steps} steps...")
        while not self.is_motion_done():
            time.sleep(poll_interval)
        return self.get_position()
    
    def move_until_power(self, target_power, power_meter, step_size=100, direction=1, max_steps=None):
        """
        Move the motor in steps until measured power exceeds target_power.
        
        Parameters:
        - target_power: desired power in W or mW
        - power_meter: instance of OphirNova2
        - step_size: number of steps to move each iteration
        - direction: +1 or -1
        - max_steps: optional limit on total number of step commands
        """
        print(f"[Axis {self.axis}] Seeking target power ≥ {target_power:.4f}...")

        current_power = power_meter.read_power()
        print(f"  Starting power: {current_power:.4f}")

        steps_taken = 0
        while current_power < target_power:
            if max_steps is not None and steps_taken >= max_steps:
                print(f"[Axis {self.axis}] Reached max_steps = {max_steps}. Stopping.")
                break
            self.move_and_wait_relative(direction * step_size)
            current_power = power_meter.read_power()
            steps_taken += 1
            print(f"  Measured power: {current_power:4f}")

        if current_power >= target_power:
            print(f"[Axis {self.axis}] Target reached at {current_power:.4f} (≥ {target_power:.4f})")
            return True
        else:
            print(f"[Axis {self.axis}] Target not reached. Final power: {current_power:.4f}")
            return False


if __name__ == '__main__':
    motor = NF8742(axis=1)

    print("Device ID:", motor.get_idn())
    print("Current position:", motor.get_position())
    # print(motor.get_velocity())
    # motor.close()
