import numpy as np
import matplotlib.pyplot as plt


class PiezoScanner:
    """
    Piezo raster scanner using a DAQ sweep backend.

    The DAQ backend must provide:
        lockin_sweep(sweep_config, timeout)
        getSweepWaveforms()

    """

    PROFILES = {
        "PI": {
            "name": "PI",
            "vmin": -2,
            "vmax": 12,
        },

        "PSJ": {
            "name": "PSJ",
            "vmin": 0,
            "vmax": 10,
        },
    }


    def __init__(
        self,
        daq,
        profile="PI",
        fast_axis_channel=1,
        slow_axis_channel=2,
        initial_wait=1,
        return_to_start=False,

        # Manual DAQ settings for now
        daq_fs=13000,
        daq_num_samples=1000,
    ):

        if profile not in self.PROFILES:
            raise ValueError(
                f"Unknown profile {profile}"
            )

        self.daq = daq

        self.profile = self.PROFILES[profile]

        self.fast_axis_channel = fast_axis_channel
        self.slow_axis_channel = slow_axis_channel

        self.initial_wait = initial_wait
        self.return_to_start = return_to_start


        # DAQ acquisition settings
        self.daq_fs = daq_fs
        self.daq_num_samples = daq_num_samples


        # Scan waveforms
        self.x_wave = None
        self.y_wave = None
        self.time = None


        # Detector
        self.detector = None


        # Metadata
        self.x_points = None
        self.y_points = None
        self.scan_time = None

        self.pixel_time = None
        self.line_time = None



    # ============================================================
    # Scan generation
    # ============================================================

    def generate_raster(
        self,
        x_points,
        y_points,
        scan_time,
        x_min=0,
        x_max=1,
        y_min=0,
        y_max=1,
    ):

        self._validate_voltage(x_min)
        self._validate_voltage(x_max)
        self._validate_voltage(y_min)
        self._validate_voltage(y_max)


        x_wave = []
        y_wave = []


        y_levels = np.linspace(
            y_min,
            y_max,
            y_points
        )


        for line, y in enumerate(y_levels):

            # triangular fast axis
            if line % 2 == 0:
                x_line = np.linspace(
                    x_min,
                    x_max,
                    x_points
                )

            else:
                x_line = np.linspace(
                    x_max,
                    x_min,
                    x_points
                )


            x_wave.extend(x_line)

            y_wave.extend(
                np.ones(x_points) * y
            )


        self.x_wave = np.asarray(x_wave)
        self.y_wave = np.asarray(y_wave)


        n = len(self.x_wave)


        self.time = np.linspace(
            0,
            scan_time,
            n
        )


        self.x_points = x_points
        self.y_points = y_points

        self.scan_time = scan_time


        self.pixel_time = (
            scan_time / n
        )

        self.line_time = (
            scan_time / y_points
        )


        return self.x_wave, self.y_wave



    # ============================================================
    # DAQ sweep configuration
    # ============================================================

    def get_sweep_config(self):

        if self.x_wave is None:
            raise RuntimeError(
                "Generate scan first"
            )


        return {

            "Sweep Time (s)": self.scan_time,

            "Initial Wait (s)": self.initial_wait,

            "Return to Start": self.return_to_start,


            "Channels": [

                {
                    "Enable?": True,
                    "Channel": self.fast_axis_channel,
                    "Start": 0,
                    "End": 0,
                    "Pattern": "Table",
                    "Table": self.x_wave.tolist(),
                },

                {
                    "Enable?": True,
                    "Channel": self.slow_axis_channel,
                    "Start": 0,
                    "End": 0,
                    "Pattern": "Table",
                    "Table": self.y_wave.tolist(),
                },

            ],
        }



    # ============================================================
    # Run sweep
    # ============================================================

    def run(self, timeout=60):

        config = self.get_sweep_config()

        self.daq.lockin_sweep(
            config,
            timeout=timeout
        )



    # ============================================================
    # Detector readout
    # ============================================================

    def read_detector(self, channel=0):

        """
        Read detector waveform.

        channel:
            index into AI list.
            AI0 = channel 0
        """

        data = self.daq.getSweepWaveforms()

        self.detector = np.asarray(
            data["AI"][channel-1]["Y"]
        )

        return self.detector



    # ============================================================
    # Detector -> image reconstruction
    # ============================================================

    def reconstruct_image(self):

        """
        Interpolate detector samples onto
        raster pixel grid.

        Returns
        -------
        image : ndarray
            shape = (y_points, x_points)
        """

        if self.detector is None:
            raise RuntimeError(
                "No detector data. "
                "Call read_detector()."
            )


        # Effective saved sample rate
        save_rate = (
            self.daq_fs /
            self.daq_num_samples
        )


        detector_time = np.arange(
            len(self.detector)
        ) / save_rate


        pixel_values = np.interp(
            self.time,
            detector_time,
            self.detector
        )


        image = pixel_values.reshape(
            self.y_points,
            self.x_points
        )


        return image



    # ============================================================
    # Plotting
    # ============================================================

    def plot(self):

        plt.figure(figsize=(10,4))

        plt.plot(
            self.time,
            self.x_wave,
            label=f"CH{self.fast_axis_channel} X"
        )

        plt.plot(
            self.time,
            self.y_wave,
            label=f"CH{self.slow_axis_channel} Y"
        )


        plt.xlabel("Time (s)")
        plt.ylabel("Voltage (V)")
        plt.grid()
        plt.legend()
        plt.tight_layout()

        plt.show()



    def plot_image(self, image):

        plt.figure()

        plt.imshow(
            image,
            origin="lower",
            aspect="auto"
        )

        plt.colorbar(
            label="Detector"
        )

        plt.xlabel("X pixel")
        plt.ylabel("Y pixel")

        plt.show()



    # ============================================================
    # Utilities
    # ============================================================

    def _validate_voltage(self, value):

        if (
            value < self.profile["vmin"]
            or value > self.profile["vmax"]
        ):

            raise ValueError(
                f"{self.profile['name']} range "
                f"is {self.profile['vmin']} to "
                f"{self.profile['vmax']} V"
            )