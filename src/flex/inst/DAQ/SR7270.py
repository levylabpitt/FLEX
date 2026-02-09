import pyvisa
import time
import numpy as np


class SR7270:
    """Driver for Stanford Research Systems SR7270 Lock-in Amplifier via USB."""
    
    _USB_RESOURCE = "USB0::0x0A2D::0x001B::{serial}::RAW"

    def __init__(self, serial: str, visa_lib=None):
        """
        Initialize SR7270 driver.
        
        Args:
            serial: SR7270 serial number (string)
            visa_lib: Optional VISA library path
        """
        self.serial = serial
        self.rm = pyvisa.ResourceManager(visa_lib) if visa_lib else pyvisa.ResourceManager()
        self.inst = None

    def open(self):
        """Open USB connection to the SR7270."""
        resource = self._USB_RESOURCE.format(serial=self.serial)
        self.inst = self.rm.open_resource(resource)
        self.inst.timeout = 10000  # 10 second timeout for large data transfers
        self.inst.chunk_size = 102400  # 100KB chunks
        return self
    
    def close(self):
        """Close the USB connection."""
        if self.inst is not None:
            try:
                self.inst.close()
            except:
                pass
            self.inst = None

    def query(self, cmd: str):
        """
        Send a command and read response.

        Returns:
            tuple: (response_str, status_byte, overload_byte)
        """
        if self.inst is None:
            raise RuntimeError("SR7270 not connected")

        # USB commands must be terminated with NULL
        self.inst.write_raw(cmd + '\x00')
        
        # Read response in chunks until NULL terminator found
        response = ""
        for _ in range(100):  # Max 100 chunks to prevent infinite loop
            try:
                chunk = self.inst.read()
                response += chunk
                
                # Check for complete termination: \x00<status><overload>
                if len(response) >= 3 and '\x00' in response:
                    null_pos = response.find('\x00')
                    if len(response) >= null_pos + 3:
                        break
            except:
                break
        
        # Parse response and extract status bytes
        if '\x00' in response:
            null_pos = response.find('\x00')
            status_byte = ord(response[null_pos + 1]) & 0x8F if len(response) >= null_pos + 2 else 0
            overload_byte = ord(response[null_pos + 2]) if len(response) >= null_pos + 3 else 0
            response_str = response[:null_pos].rstrip()
        else:
            status_byte = overload_byte = 0
            response_str = response.rstrip()

        return response_str, status_byte, overload_byte

    # ------------------------------------------------------------
    # Basic queries
    # ------------------------------------------------------------

    def get_id(self):
        """Get instrument identification string."""
        return self.query("ID")[0]

    def get_ver(self):
        """Get instrument firmware version."""
        return self.query("VER")[0]

    # ------------------------------------------------------------
    # Reference / Oscillator
    # ------------------------------------------------------------

    def set_ref_frequency(self, freq_hz: float):
        """Set internal oscillator frequency in Hz."""
        self.query(f"FRQ {freq_hz}")

    def get_ref_frequency(self) -> float:
        """Get internal oscillator frequency in Hz."""
        return float(self.query("FRQ.")[0])

    def set_ref_amplitude(self, amp_volts: float):
        """Set oscillator amplitude in Volts."""
        self.query(f"OA {amp_volts}")

    def get_ref_amplitude(self) -> float:
        """Get oscillator amplitude in Volts."""
        return float(self.query("OA.")[0])

    def set_ref_phase(self, phase_deg: float):
        """Set reference phase shift in degrees."""
        self.query(f"REFP. {phase_deg}")

    def get_ref_phase(self) -> float:
        """Get reference phase shift in degrees."""
        return float(self.query("REFP.")[0])

    # ------------------------------------------------------------
    # Signal Channel Setup
    # ------------------------------------------------------------

    def set_sensitivity(self, index: int):
        """Set full-scale sensitivity range (1-27, see manual)."""
        self.query(f"SEN {index}")

    def get_sensitivity(self) -> int:
        """Get current sensitivity range index."""
        return int(self.query("SEN")[0])

    def set_time_constant(self, index: int):
        """Set output time constant (0-29, see manual)."""
        self.query(f"TC {index}")

    def get_time_constant(self) -> int:
        """Get current time constant index."""
        return int(self.query("TC")[0])

    def auto_measure(self):
        """Perform Auto-Measure (ASM) operation."""
        self.query("ASM")

    # ------------------------------------------------------------
    # Single-point Data Acquisition
    # ------------------------------------------------------------

    def get_x(self) -> float:
        """Get X channel output in Volts."""
        return float(self.query("X.")[0])

    def get_y(self) -> float:
        """Get Y channel output in Volts."""
        return float(self.query("Y.")[0])

    def get_magnitude(self) -> float:
        """Get magnitude output in Volts."""
        return float(self.query("MAG.")[0])

    def get_phase(self) -> float:
        """Get phase output in degrees."""
        return float(self.query("PHA.")[0])

    def get_xy(self):
        """Get (X, Y) tuple in Volts."""
        return self.get_x(), self.get_y()

    def get_rtheta(self):
        """Get (Magnitude, Phase) tuple."""
        return self.get_magnitude(), self.get_phase()

    # ------------------------------------------------------------
    # Continuous Data Acquisition (Curve Buffer)
    # ------------------------------------------------------------

    def setup_curve_buffer(self, buffer_size: int):
        """
        Set curve buffer length.
        
        Args:
            buffer_size: Number of points to store (max 100000)
        """
        self.query(f"LEN {buffer_size}")

    def configure_curve_quantity(self, cbd_value: int):
        """
        Configure what quantities to store in curve buffer.
        
        NOTE: For floating point readout (DC. command), bit 4 (Sensitivity=16)
        MUST be included when storing X, Y, Magnitude, or Noise.
        
        Args:
            cbd_value: Bit mask - combine with bitwise OR:
                      1=X, 2=Y, 4=Mag, 8=Phase, 16=Sensitivity,
                      32=ADC1, 64=ADC2, 128=ADC3
                      
        Examples:
            17 (1+16): X + Sensitivity (floating point)
            19 (1+2+16): X + Y + Sensitivity (floating point)
        """
        self.query(f"CBD {cbd_value}")

    def set_storage_interval(self, interval_us: float):
        """
        Set time interval between data points.
        
        Args:
            interval_us: Interval in microseconds (min 1000 µs = 1 ms)
        """
        self.query(f"STR {interval_us}")

    def start_continuous_acquisition(self, mode: int = 0):
        """
        Start continuous data acquisition.
        
        Args:
            mode: 0=start immediately, 1=start on trigger, 2=triggered start/stop
        """
        self.query(f"TDC {mode}")

    def halt_acquisition(self):
        """Stop curve acquisition."""
        self.query("HC")

    def get_acquisition_status(self):
        """
        Get curve acquisition status.
        
        Returns:
            tuple: (status, num_sweeps, status_byte, num_points)
                status: 0=idle, 2=running, 6=halted
                num_points: Number of points acquired
        """
        resp = self.query("M")[0]
        return tuple(int(x.strip()) for x in resp.split(','))

    def get_num_stored_points(self) -> int:
        """Get number of points stored in buffer."""
        return self.get_acquisition_status()[3]

    def read_curve_buffer(self, bit_number: int):
        """
        Read data from curve buffer.
        
        Args:
            bit_number: Bit position from CBD (0=X, 1=Y, 2=Mag, 3=Phase, etc.)
        
        Returns:
            list of float values
        """
        resp = self.query(f"DC. {bit_number}")[0]
        if not resp:
            return []
        
        values = []
        for line in resp.split('\n'):
            line = line.strip()
            if line:
                try:
                    values.append(float(line))
                except ValueError:
                    pass
        return values

    def clear_curve_buffer(self):
        """Clear the curve buffer."""
        self.query("NC")

    def acquire_continuous(self, duration_s: float, sample_rate_hz: float, channel: str = 'X'):
        """
        Perform continuous data acquisition and return time-series data.
        
        Args:
            duration_s: Acquisition duration in seconds
            sample_rate_hz: Sample rate in Hz (max 1000 Hz)
            channel: Channel to acquire ('X', 'Y', 'Mag', or 'Phase')
        
        Returns:
            tuple: (timestamps, values) as numpy arrays
                timestamps: Time array in seconds
                values: Measured values in Volts (or degrees for Phase)
        
        Example:
            times, x_vals = sr.acquire_continuous(duration_s=10.0, sample_rate_hz=100)
        """
        # Calculate parameters
        num_points = int(duration_s * sample_rate_hz)
        interval_us = int(1e6 / sample_rate_hz)  # Convert Hz to microseconds
        
        # Map channel to CBD bit mask and bit number
        channel_map = {
            'X': (17, 0),      # X + Sensitivity, read bit 0
            'Y': (18, 1),      # Y + Sensitivity, read bit 1
            'Mag': (20, 2),    # Mag + Sensitivity, read bit 2
            'Phase': (8, 3)    # Phase only (no sensitivity needed), read bit 3
        }
        
        if channel not in channel_map:
            raise ValueError(f"Channel must be one of {list(channel_map.keys())}")
        
        cbd_value, bit_number = channel_map[channel]
        
        # Setup and acquire
        self.clear_curve_buffer()
        self.setup_curve_buffer(min(num_points, 100000))  # Max 100k points
        self.configure_curve_quantity(cbd_value)
        self.set_storage_interval(interval_us)
        
        self.start_continuous_acquisition(0)
        time.sleep(duration_s)
        self.halt_acquisition()
        
        # Retrieve data
        values = np.array(self.read_curve_buffer(bit_number))
        timestamps = np.arange(len(values)) / sample_rate_hz
        
        return timestamps, values

    # ------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------

    def __enter__(self):
        return self.open()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    serial_number = "10105267"
    
    with SR7270(serial_number) as sr:
        print(f"Connected to {sr.get_id()}")
        
        # Simple one-liner acquisition
        times, x_data = sr.acquire_continuous(duration_s=10.0, sample_rate_hz=100, channel='X')
        
        print(f"Acquired {len(x_data)} points")
        print(f"Mean: {np.mean(x_data):.3e} V")
        print(f"Std: {np.std(x_data):.3e} V")
        
        # Save
        np.savetxt('lockin_scan.csv', 
                   np.column_stack([times, x_data]), 
                   delimiter=',', 
                   header='time(s),X(V)',
                   comments='')