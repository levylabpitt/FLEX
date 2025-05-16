import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import igor.binarywave as ibw
from flex.db import FLEXDB


class AFMImageLoader:
    """Class to handle loading and processing AFM images from IBW files."""
    
    def __init__(self, file_path):
        """
        Initialize with an IBW file path.
        
        Args:
            file_path (str): Path to the IBW file
        """
        self.file_path = file_path
        self.ibw_data = None
        self.wave = None
        self.wave_norm = None
        self.header = None
        self.note = ""
        self.extent = None
        self.unit_x = ""
        self.unit_y = ""
        
    def load(self):
        """Load IBW file and extract relevant data."""
        self.ibw_data = ibw.load(self.file_path)
        wave_all = self.ibw_data['wave']['wData']
        self.header = self.ibw_data['wave']['wave_header']
        
        # Extract notes
        note_raw = self.ibw_data['wave'].get('note', b'')
        self.note = note_raw.decode('utf-8', errors='ignore')
        self._extract_units_from_note()
        
        # Select one layer if 3D
        if wave_all.ndim == 3 and wave_all.shape[2] >= 1:
            self.wave = wave_all[:, :, 0]  # Use the first channel by default
        else:
            self.wave = wave_all
            
        # Calculate physical dimensions
        self._calculate_physical_dimensions()
        
        # Normalize wave data
        self._normalize_wave()
        
        return self
    
    def _extract_units_from_note(self):
        """Extract units from the note field."""
        for line in self.note.splitlines():
            if "X Units:" in line:
                self.unit_x = line.split(":")[1].strip()
            if "Y Units:" in line:
                self.unit_y = line.split(":")[1].strip()
    
    def _calculate_physical_dimensions(self):
        """Calculate physical dimensions and extent from header data."""
        n_x = self.header['nDim'][0]           # number of x points
        n_y = self.header['nDim'][1]           # number of y points
        x_delta = self.header['sfA'][0]        # x step size
        x_origin = self.header['sfB'][0]       # x origin
        y_delta = self.header['sfA'][1]        # y step size
        y_origin = self.header['sfB'][1]       # y origin
        
        # Construct physical axes
        x = x_origin + np.arange(n_x) * x_delta
        y = y_origin + np.arange(n_y) * y_delta
        self.extent = [x[0], x[-1], y[0], y[-1]]
    
    def _normalize_wave(self):
        """Normalize wave data to [0,1] for imshow."""
        self.wave = self.wave.astype(np.float32)
        wave_min = np.nanmin(self.wave)
        wave_max = np.nanmax(self.wave)

        if wave_max == wave_min:
            self.wave_norm = np.zeros_like(self.wave)
        else:
            self.wave_norm = (self.wave - wave_min) / (wave_max - wave_min)
            
        # Reorient image for display
        self.wave_norm = np.fliplr(np.rot90(self.wave_norm, k=-1))
    
    def get_display_data(self):
        """Return the data needed for display."""
        return {
            'wave_norm': self.wave_norm,
            'extent': self.extent,
            'unit_x': self.unit_x,
            'unit_y': self.unit_y
        }


class TipTraceData:
    """Class to handle tip trace data retrieval and processing."""
    
    def __init__(self, db_name, user):
        """
        Initialize with database connection parameters.
        
        Args:
            db_name (str): Database name
            user (str): Database user
        """
        self.db_name = db_name
        self.user = user
        self.db = None
        self.segments = []
        self.frames = []
        
    def fetch_data(self, start_time, end_time, table):
        """
        Fetch tip trace data from database.
        
        Args:
            start_time (str): Start time for data query
            end_time (str): End time for data query
            table (str): Database table name
        """
        self.db = FLEXDB(self.db_name, self.user)
        query = """
            SELECT time, d000, d001, d002, d003, v002
            FROM {}
            WHERE time BETWEEN %s AND %s
            ORDER BY time ASC
        """.format(table)
        rows = self.db.execute_fetch(query, params=(start_time, end_time), method='all')
        self.db.close_connection()
        
        self._extract_segments(rows)
        self._create_frames()
        
        return self
    
    def _extract_segments(self, rows):
        """Extract trace segments from database rows."""
        current_points = []
        for row in rows:
            timestamp, x, y, speed, voltage, path_name = row
            if all(v is None for v in [speed, voltage, path_name]) and None not in (x, y):
                current_points.append((x, y + 20e-6))  # Flip Y to match image orientation
            elif any(v is not None for v in [speed, voltage, path_name]):
                if current_points:
                    self.segments.append({
                        "start_time": timestamp,
                        "speed": speed,
                        "voltage": voltage,
                        "path_name": path_name,
                        "points": current_points[::-1]  # Reverse order to match image orientation
                    })
                    current_points = []
                    
        if not self.segments:
            raise ValueError("No valid segments found in the specified time range.")
    
    def _create_frames(self):
        """Convert segments into animation frames."""
        for seg in self.segments:
            color = self._determine_segment_color(seg["voltage"])
            for point in seg["points"]:
                self.frames.append((point[0], point[1], color, seg["path_name"], seg["voltage"]))
    
    def _determine_segment_color(self, voltage):
        """Determine segment color based on voltage."""
        if voltage is None:
            return 'gray'
        return 'green' if voltage < 0 else 'red'
    
    def plot_segments(self, max_segments=3):
        """
        Plot the first few segments for quick visualization.
        
        Args:
            max_segments (int): Maximum number of segments to plot
        """
        for i, seg in enumerate(self.segments[:max_segments]):
            x = [pt[0] for pt in seg['points']]
            y = [pt[1] for pt in seg['points']]
            plt.figure()
            plt.plot(x, y, '-o')
            plt.title(f"Segment {i}: {seg['path_name']}")
            plt.xlabel("X")
            plt.ylabel("Y")
            plt.gca().set_aspect('equal')
            plt.show()


class AFMAnimator:
    """Class to handle the creation and display of AFM animations."""
    
    def __init__(self, afm_image, tip_trace):
        """
        Initialize with AFM image and tip trace data.
        
        Args:
            afm_image (AFMImageLoader): Processed AFM image
            tip_trace (TipTraceData): Processed tip trace data
        """
        self.afm_data = afm_image.get_display_data()
        self.frames = tip_trace.frames
        
        self.fig = None
        self.ax = None
        self.im = None
        self.trace_lines = []
        self.x_segments = [[]]
        self.y_segments = [[]]
        self.colors = []
        self.tip_dot = None
        self.tip_label = None
        self.segment_label = None
        self.animation = None
        self.current_path = [None]
    
    def setup_figure(self):
        """Set up the figure and animation elements."""
        self.fig, self.ax = plt.subplots(figsize=(6, 5))
        
        # Display the AFM image
        self.im = self.ax.imshow(
            self.afm_data['wave_norm'], 
            cmap='gray', 
            origin='lower', 
            extent=self.afm_data['extent']
        )
        plt.colorbar(self.im, ax=self.ax, label='Normalized Height')
        
        # Create animation elements
        self.tip_dot = self.ax.scatter([], [], s=80, color='red')
        self.tip_label = self.ax.text(0.02, 0.95, '', transform=self.ax.transAxes)
        self.segment_label = self.ax.text(0.02, 0.90, '', transform=self.ax.transAxes)
        
        # Set labels and title
        self.ax.set_title("AFM Image with Animated Tip Trace")
        x_label = f"X [{self.afm_data['unit_x']}]" if self.afm_data['unit_x'] else "X (arb. units)"
        y_label = f"Y [{self.afm_data['unit_y']}]" if self.afm_data['unit_y'] else "Y (arb. units)"
        self.ax.set_xlabel(x_label)
        self.ax.set_ylabel(y_label)
        
        return self
    
    def init_animation(self):
        """Initialize animation state - called at the start of the animation."""
        for line in self.trace_lines:
            line.remove()
        self.trace_lines.clear()
        self.x_segments.clear()
        self.y_segments.clear()
        self.x_segments.append([])
        self.y_segments.append([])
        self.colors.clear()
        self.tip_dot.set_offsets(np.empty((0, 2)))
        self.tip_label.set_text("")
        self.segment_label.set_text("")
        return self.trace_lines + [self.tip_dot, self.tip_label, self.segment_label]
    
    def update_animation(self, frame):
        """Update animation for each frame."""
        x, y, color, path, voltage = frame

        # Check if we need to start a new segment
        if path != self.current_path[0]:
            self.current_path[0] = path
            self.x_segments.append([])
            self.y_segments.append([])
            self.colors.append(color)
            self.trace_lines.append(self.ax.plot([], [], lw=1.5, alpha=0.9, color=color)[0])

        # If there are no trace lines yet, create the first one
        if not self.trace_lines:
            self.trace_lines.append(self.ax.plot([], [], lw=1.5, alpha=0.9, color=color)[0])
            self.colors.append(color)

        # Update the current segment with new point
        self.x_segments[-1].append(x)
        self.y_segments[-1].append(y)
        self.trace_lines[-1].set_data(self.x_segments[-1], self.y_segments[-1])

        # Update tip position and labels
        self.tip_dot.set_offsets([[x, y]])
        voltage_text = f"Voltage: {voltage:.3f} V" if voltage is not None else ""
        self.tip_label.set_text(voltage_text)
        path_text = f"Path: {path}" if path else ""
        self.segment_label.set_text(path_text)

        return self.trace_lines + [self.tip_dot, self.tip_label, self.segment_label]
    
    def create_animation(self):
        """Create the animation."""
        self.animation = animation.FuncAnimation(
            self.fig, 
            self.update_animation, 
            frames=self.frames, 
            init_func=self.init_animation,
            interval=0.001, 
            blit=True, 
            repeat=False
        )
        return self
    
    def display(self):
        """Display the animation."""
        plt.tight_layout()
        plt.show()


def main():
    """Main function to run the AFM viewer."""
    # Load AFM image
    afm_image = AFMImageLoader("./tests/afm_viewer/ahmed/SA405230014.ibw").load()
    
    # Fetch tip trace data
    # start_time = '2025-04-16 17:00:00 -0400'
    # end_time = '2025-04-16 19:00:00 -0400'
    # start_time = '2025-04-22 14:30:00 -0400'
    # end_time = '2025-04-22 16:00:00 -0400'
    start_time = '2025-05-01 18:30:00 -0400'
    end_time = '2025-05-01 19:00:00 -0400'
    tip_trace = TipTraceData("levylab", "llab_admin").fetch_data(start_time, end_time, "llab_079")
    
    # Display first few segments for debugging
    # tip_trace.plot_segments(max_segments=3)
    
    # Create and display the animation
    animator = AFMAnimator(afm_image, tip_trace)
    animator.setup_figure().create_animation().display()


if __name__ == "__main__":
    main()