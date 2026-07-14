from flex.exp.PiezoScanner import PiezoScanner
from flex.inst.levylab.Lockin import Lockin


daq = Lockin()

scanner = PiezoScanner(
    daq=daq,
    profile="PI",
    fast_axis_channel=2,
    slow_axis_channel=5,

    daq_fs=13000,
    daq_num_samples=1000
)


scanner.generate_raster(
    x_points=200,
    y_points=200,
    scan_time=10,
    x_min=0,
    x_max=0.1,
    y_min=0,
    y_max=0.1
)

scanner.plot()

scanner.run()

data = scanner.read_detector(
    channel=1
)

image = scanner.reconstruct_image()

scanner.plot_image(image)