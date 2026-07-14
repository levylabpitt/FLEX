from flex.exp.pund import PUNDConfig, PUNDMeasurement
import matplotlib.pyplot as plt

_AMP_GAIN = 25
_KH_SHUNT_RES = 50
_KH_GAIN = 1
x = 1000

cfg = PUNDConfig(
    sample_id='SA40XXX',
    daq_name='Dev2',
    amplitude=0.7,      # Volts
    signal_freq=1000,   # Hz
    duration=0.001,     # seconds
    waveform='triangle',
    save_to_file=True,
    save_path=r"C:\Users\voodoo\Desktop\Aswini_PUND_Data"
)
result = PUNDMeasurement(cfg).run()

plt.figure(figsize=(10,5))
plt.plot(result['ao']*_AMP_GAIN, (x*result['ai'])/(_KH_SHUNT_RES*_KH_GAIN), color='tab:blue', marker='o')
plt.ylabel('Current (mA)')
plt.xlabel('Voltage (V)')
plt.grid(True, alpha=0.5)
plt.show()