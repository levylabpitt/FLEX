#%% - Imports and Inst Init
from flex.exp.CESession import CESession
import numpy as np
from flex.inst.levylab.PPMSW1 import PPMSW1
from flex.inst.levylab.TransportServer import Transport
from flex.inst.levylab.Lockin import Lockin
import time

exp = CESession()

ppms = exp.Temperature
lockin = exp.DAQ
transport = exp.Transport

ppms = PPMSW1()
lockin = Lockin()
transport = Transport()


#%% - Helper Functions
def setT_withTol(temp_K, rate_K_per_min, tol_K):
    print(f'Setting T to {temp_K} at {rate_K_per_min}')
    ppms.setTemperature(temp_K, rate_K_per_min)
    while True:
        rb = ppms.getTemperature()
        cur = rb.get('temperature')
        if cur is not None and abs(temp_K - cur) <= tol_K:
            print("temperature reached.")
            break
        time.sleep(1)

def setB_withTol(field_T, rate_T_per_min, tol_T):
    print(f'Setting B to {field_T} at {rate_T_per_min}')
    ppms.setMagnet(field_T, rate_T_per_min)
    while True:
        rb = ppms.getMagnet()
        cur = rb.get('field')
        if cur is not None and abs(field_T - cur) <= tol_T:
            break
        time.sleep(1)


#%% - Param Definition
BG_CHANNEL = 5  # Channel
BG_RATE = 20    # Seconds/Volt
BG_START = 0    # Volts
BG_END = 2      # Volts
BG_STEP = 0.01  # Volts

B_START = 9    # Tesla
B_END = 5e-3       # Tesla
B_RATE = 0.3    # Tesla/min
B_TOL = 0.0005  # Tesla

T_START = 1.15  # Kelvins
T_END = 4       # Kelvins
T_STEP = 0.05   # Kelvins
T_TOL = 0.002   # Kelvins
T_RATE = 0.05   # Kelvins/min
T_RATE_BACK = 0.2 # Kelvins/min

bg_array = np.arange(BG_START, BG_END, BG_STEP)


#%% - Experiments
for bg in bg_array:
    setT_withTol(T_START, T_RATE_BACK, T_TOL)
    lockin.set_backgate(BG_CHANNEL, bg, BG_RATE)

    exp_folder   = f"03 - Sweep Vbg\\R vs B\\BG_{bg:.2f} "
    exp_comments = f"""									
    I+/-: 2/26 7mV 13 Hz
    V1+/-: 1/27 Diff (KH1)
    V2+/-: 1/3 Diff (KH3)
    V3+/-: 27/5 Diff (KH7)
    Vbg:{BG_CHANNEL} = {bg:.2f}V
    Continuous B Sweep from -5T to +5T, 0.3T/min, 
    """
    transport.setExptFolder(exp_folder)
    transport.setExptComments(exp_comments)

    setB_withTol(field_T=B_START, rate_T_per_min=B_RATE, tol_T=B_TOL)
    print(f'Magnet is at {B_START}., Initiating Measurement: Setting Magnet to {B_END}')
    transport.startTransport('LockinTime')
    ppms.setMagnet(field=B_END, rate=B_RATE)
    while abs(ppms.getMagnet()['field'] - B_END) > B_TOL:
        time.sleep(1)
    transport.stopTransport()
    

# %%
exp.close_all()