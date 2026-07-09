"""Rotrics DexArm robot arm over a serial port (G-code protocol)."""

from __future__ import annotations

import re

from flex_protocols import SerialInstrument


class DexArm(SerialInstrument):
    """Rotrics DexArm robot arm.

    Speaks G-code over serial at 115200 baud. Commands embed their own
    terminators (``\\r`` / ``\\r\\n``) exactly as the firmware expects, and the
    arm acknowledges each command with a line containing ``ok`` — so this
    driver talks to the serial port directly through :meth:`_send_cmd` rather
    than the line-oriented base ``write``/``read``.
    """

    def __init__(self, name: str = "dexarm", port: str = "", *, timeout: float | None = None, **kwargs):
        """
        Args:
            name: Instrument name used in logs, snapshots, and experiments.
            port: The serial port of the DexArm, e.g. ``"COM3"``.
            timeout: Read timeout in seconds; ``None`` (default) blocks until
                the arm responds, as the arm can take arbitrarily long to
                acknowledge motion commands.
        """
        super().__init__(name, port, baudrate=115200, timeout=timeout, **kwargs)
        self.add_parameter(
            "position",
            getter=self.get_current_position,
            doc="Current position (x, y, z, e, theta_a, theta_b, theta_c).",
        )

    def _send_cmd(self, data: str, wait: bool = True) -> None:
        """Send a command to the arm.

        Args:
            data: The command, including its terminator.
            wait: Wait for the arm to acknowledge with ``ok``. If True, this
                blocks until the arm responds. If False, it returns
                immediately, but the command could be ignored if the arm's
                buffer is full.
        """
        self.log.debug("write: %r", data)
        self._serial.write(data.encode())
        if not wait:
            self._serial.reset_input_buffer()
            return
        while True:
            serial_str = self._serial.readline().decode("utf-8")
            if len(serial_str) > 0:
                if serial_str.find("ok") > -1:
                    self.log.debug("read ok")
                    break
                self.log.debug("read: %s", serial_str.strip())

    def go_home(self) -> None:
        """Go to the home position and enable the motors.

        Should be called each time the arm is powered on.
        """
        self._send_cmd("M1112\r")

    def set_workorigin(self) -> None:
        """Set the current position as the new work origin."""
        self._send_cmd("G92 X0 Y0 Z0 E0\r")

    def set_acceleration(
        self, acceleration: int, travel_acceleration: int, retract_acceleration: int = 60
    ) -> None:
        """Set the preferred starting acceleration for moves of different types.

        Args:
            acceleration: Printing acceleration. Used for moves that employ
                the current tool.
            travel_acceleration: Used for moves that include no extrusion.
            retract_acceleration: Used for extruder retraction moves.
        """
        cmd = (
            "M204"
            + "P"
            + str(acceleration)
            + "T"
            + str(travel_acceleration)
            + "T"
            + str(retract_acceleration)
            + "\r\n"
        )
        self._send_cmd(cmd)

    def set_module_type(self, module_type: int) -> None:
        """Set the type of end effector.

        Args:
            module_type: 0 for pen holder module, 1 for laser engraving
                module, 2 for pneumatic module, 3 for 3D printing module.
        """
        self._send_cmd("M888 P" + str(module_type) + "\r")

    def get_module_type(self) -> str | None:
        """Get the type of end effector.

        Returns:
            'PEN', 'LASER', 'PUMP', or '3D' (None if the arm did not report
            a recognized module before acknowledging).
        """
        self._serial.reset_input_buffer()
        self._serial.write(b"M888\r")
        module_type = None
        while True:
            serial_str = self._serial.readline().decode("utf-8")
            if len(serial_str) > 0:
                if serial_str.find("PEN") > -1:
                    module_type = "PEN"
                if serial_str.find("LASER") > -1:
                    module_type = "LASER"
                if serial_str.find("PUMP") > -1:
                    module_type = "PUMP"
                if serial_str.find("3D") > -1:
                    module_type = "3D"
                if serial_str.find("ok") > -1:
                    return module_type

    def move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        e: float | None = None,
        feedrate: int = 2000,
        mode: str = "G1",
        wait: bool = True,
    ) -> None:
        """Move to a cartesian position.

        Adds a linear move to the queue, performed after all previous moves
        complete.

        Args:
            mode: ``"G1"`` (default) or ``"G0"`` for fast mode.
            x, y, z, e: The position, in millimeters by default. Units may be
                set to inches by G20. Note that the center of the y axis is
                300 mm.
            feedrate: Sets the feedrate for all subsequent moves.
            wait: Block until the arm acknowledges the move.
        """
        cmd = mode + "F" + str(feedrate)
        if x is not None:
            cmd = cmd + "X" + str(round(x))
        if y is not None:
            cmd = cmd + "Y" + str(round(y))
        if z is not None:
            cmd = cmd + "Z" + str(round(z))
        if e is not None:
            cmd = cmd + "E" + str(round(e))
        cmd = cmd + "\r\n"
        self._send_cmd(cmd, wait=wait)

    def fast_move_to(
        self,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        feedrate: int = 2000,
        wait: bool = True,
    ) -> None:
        """Fast move to a cartesian position, i.e. in mode G0.

        Args:
            x, y, z: The position, in millimeters by default.
            feedrate: Sets the feedrate for all subsequent moves.
            wait: Block until the arm acknowledges the move.
        """
        self.move_to(x=x, y=y, z=z, feedrate=feedrate, mode="G0", wait=wait)

    def get_current_position(
        self,
    ) -> tuple[
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
        float | None,
    ]:
        """Get the current position.

        Returns:
            Position ``(x, y, z)``, extrusion ``e``, and DexArm theta
            ``(a, b, c)``.
        """
        self._serial.reset_input_buffer()
        self._serial.write(b"M114\r")
        x, y, z, e, a, b, c = None, None, None, None, None, None, None
        while True:
            serial_str = self._serial.readline().decode("utf-8")
            if len(serial_str) > 0:
                if serial_str.find("X:") > -1:
                    temp = re.findall(r"[-+]?\d*\.\d+|\d+", serial_str)
                    x = float(temp[0])
                    y = float(temp[1])
                    z = float(temp[2])
                    e = float(temp[3])
                if serial_str.find("DEXARM Theta") > -1:
                    temp = re.findall(r"[-+]?\d*\.\d+|\d+", serial_str)
                    a = float(temp[0])
                    b = float(temp[1])
                    c = float(temp[2])
                if serial_str.find("ok") > -1:
                    return x, y, z, e, a, b, c

    def delay_ms(self, value: int) -> None:
        """Pause the command queue and wait for a period of time in ms.

        Args:
            value: Time in ms.
        """
        self._send_cmd("G4 P" + str(value) + "\r")

    def delay_s(self, value: int) -> None:
        """Pause the command queue and wait for a period of time in s.

        Args:
            value: Time in s.
        """
        self._send_cmd("G4 S" + str(value) + "\r")

    def soft_gripper_pick(self) -> None:
        """Close the soft gripper."""
        self._send_cmd("M1001\r")

    def soft_gripper_place(self) -> None:
        """Wide-open the soft gripper."""
        self._send_cmd("M1000\r")

    def soft_gripper_nature(self) -> None:
        """Release the soft gripper to its natural state."""
        self._send_cmd("M1002\r")

    def soft_gripper_stop(self) -> None:
        """Stop the soft gripper."""
        self._send_cmd("M1003\r")

    def air_picker_pick(self) -> None:
        """Pick up an object."""
        self._send_cmd("M1000\r")

    def air_picker_place(self) -> None:
        """Release an object."""
        self._send_cmd("M1001\r")

    def air_picker_nature(self) -> None:
        """Release to natural state."""
        self._send_cmd("M1002\r")

    def air_picker_stop(self) -> None:
        """Stop the picker."""
        self._send_cmd("M1003\r")

    def laser_on(self, value: int = 0) -> None:
        """Turn on the laser.

        Args:
            value: Set the power, range from 1 to 255.
        """
        self._send_cmd("M3 S" + str(value) + "\r")

    def laser_off(self) -> None:
        """Turn off the laser."""
        self._send_cmd("M5\r")

    # Conveyor Belt

    def conveyor_belt_forward(self, speed: int = 0) -> None:
        """Move the belt forward."""
        self._send_cmd("M2012 F" + str(speed) + "D0\r")

    def conveyor_belt_backward(self, speed: int = 0) -> None:
        """Move the belt backward."""
        self._send_cmd("M2012 F" + str(speed) + "D1\r")

    def conveyor_belt_stop(self, speed: int = 0) -> None:
        """Stop the belt."""
        self._send_cmd("M2013\r")

    # Sliding Rail

    def sliding_rail_init(self) -> None:
        """Initialize the sliding rail."""
        self._send_cmd("M2005\r")
