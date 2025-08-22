#%% Imports
from flex.inst import *
import time
import numpy as np
import matplotlib.pyplot as plt
from tqdm import tqdm
import os

#%% Initialize Instruments
lockin = MCLockin()
kh = KH7008()
transport = Transport()

dscan = DScan("DM240913")
ophir = OphirNova2()
newfocus = NF8742(axis=1)

# %% Experiment variables and functions
def insertion_sweep(start, stop, step, file_suffix, lockin_measure_channel=1, save_path=None, notes=None):
    """
    Sweep the insertion from start to stop with a given step size.
    """
    insertion = np.arange(start, stop, step)
    pv = []

    for i in tqdm(insertion, desc="Scanning insertion..."):
        dscan.set_insertion(i)
        time.sleep(0.5)
        pv.append(lockin.get_lockin(lockin_measure_channel, 'Mean'))
        # pv.append(pm.read_power())

    # Saving to a file
    filename = f"{time.strftime('%H%M%S')}_{file_suffix}.txt"
    file_path = os.path.join(save_path, filename)
    combined_array = np.column_stack((insertion, pv))
    np.savetxt(file_path, combined_array, delimiter='\t', header='Insertion (mm),Photocurrent (A)')

    # Saving metadata
    if notes:
        notes = \
            f"""
            This is a test script for the DScan and MCLockin instruments.
            """
        with open(f"{file_path}_notes.txt", "w") as file:
            file.write(notes)

    return insertion, pv

def run_timedelay(exp_folder="", comments="", tdms_params=""):
    """
    Run the time delay experiment.
    """
    lv.callTransport(exp_folder=exp_folder, comments=comments, tdms_params=tdms_params, VI="THz_TimeDelay")
device_folder = r'G:\.shortcut-targets-by-id\0B8-gGFa6hkR4XzJJMDlqZXVKRk0\ansom\Data\THz 1\SA40458.20250806'

#%% Experiment 1 - PC vs. Insertion (single)
"""
Sets Insertion -> Take Photocurrent Data
"""

experiment_folder = r'PCsvIns\0821'
exp1_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp1_save_path):
    os.makedirs(exp1_save_path)

# data_link = nc.get_file_link(nc_link, experiment_folder)
with Measurement(data_folder=exp1_save_path, notes="PC vs Ins Test"):
    # power = pm.read_power()
    ins_a, pv_a = insertion_sweep(start=20, stop=50, step=0.1, file_suffix=f"100mBias_T288K", lockin_measure_channel=3, save_path=exp1_save_path)

    plt.plot(ins_a, pv_a)
    plt.xlabel('Insertion (mm)')
    plt.ylabel('Photocurrent (A)')
    plt.show()

#%% Experiment 2 - SD Bias vs. PC vs. Insertion
"""
Sets SD Bias -> Takes PC vs. Insertion Data
"""

experiment_folder = '20250818_Bias vs PC vs Insertion_T6K'
exp2_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp2_save_path):
    os.makedirs(exp2_save_path)

sd_bias = np.arange(-0.14, 0.5, 0.01)
for value in sd_bias:
    lockin.set_dc(1, value)
    # for _ in range(5):
    file_suffix = f"Bias={value}"
    insertion, pc = insertion_sweep(start=30, stop=50, step=0.1, file_suffix=file_suffix, lockin_measure_channel=3, save_path=exp2_save_path)
    plt.plot(insertion, pc)
    plt.xlabel('Insertion (mm)')
    plt.ylabel('Photocurrent (A)')
    plt.show()


# %% Experiment 3 - Insertion vs. Time Delay
"""
Sets Insertion -> Takes Time Delay Data 
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""

experiment_folder = '99'

insertion_array = np.arange(0, 0.3, 0.2)
for insertion in tqdm(insertion_array, desc="Scanning insertion..."):
    dscan.set_insertion(insertion)
    time.sleep(0.2)
    run_timedelay(exp_folder=experiment_folder, tdms_params={"Insertion": insertion})



# %% Experiment 4 - Insertion (Interleaved) vs. Time Delay
"""
Sets Insertion -> Takes TD -> Goes to the reference insertion -> Takes TD -> Goes to the next insertion
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""

experiment_folder = '02 - 20250808_WingExp_6K_50mBias'

ref_insertion = 35
insertion_array = np.arange(0, 90, 1)
ref_counter = 1
for insertion in tqdm(insertion_array, desc="Scanning insertion..."):
    dscan.set_insertion(insertion)
    ins = float(insertion)
    # power = pm.read_power()
    run_timedelay(exp_folder=experiment_folder, tdms_params={"Insertion":ins})
    # if ref_counter % 10 == 0:
    #     dscan.set_insertion(ref_insertion)
    #     power = pm.read_power()
    #     run_timedelay(exp_folder=f"{experiment_folder}\\refence_scans", tdms_params={"Insertion":ins, "Power":power})
    # ref_counter += 1


# %% Experiment 5 - Power vs. Dispersion
insertion = np.arange(3,10,0.1)
power = []

for i in tqdm(insertion, desc="Scanning insertion..."):
    dscan.set_insertion(i)
    time.sleep(0.1)
    power.append(pm.read_power())

plt.plot(insertion, power)
plt.xlabel('Insertion (mm)')
plt.ylabel('Power (W)')
plt.title('Power vs Insertion')
plt.show()

# %% Experiment 6 - Insertion (Interleaved) vs. Time Delay (Automated Power)
"""
Sets Insertion -> Takes TD -> Goes to the reference insertion -> Takes TD -> Goes to the next insertion
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""

ref_insertion = 35
insertion_array = np.arange(2, 12, .1)
power_array = np.arange(0.0010, 0.0022, 0.0002)
for power in power_array:
    power_set = nf.move_until_power(power,pm,50,1,50)
    if power_set:
        cur_power = pm.read_power()
        experiment_folder = f'20250416_IntInsTD_P_{cur_power:.4f}_smallTDrange'
        ref_counter = 1
        for i in tqdm(insertion_array, desc="Scanning insertion..."):
            dscan.set_insertion(i)
            curr_power = pm.read_power()
            run_timedelay(exp_folder=experiment_folder, comments=f"Insertion={i}:Power={curr_power:4f}")
            if ref_counter % 10 == 0:
                dscan.set_insertion(ref_insertion)
                run_timedelay(exp_folder=f"{experiment_folder}\\reference_scans", comments=f"Reference after insertion={i}")
            ref_counter += 1
    else:
        break

# %% Experiment 7 - TimeDelay vs CEP @ Optimum Insertion
"""
Set Optimum Insertion/Max power
Change CEP -> Takes TD
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""
insertion = 6
cep_array = np.arange(0,15.1,0.1)
experiment_folder = f'0501_TimeDelayvsCEP'
for cep in tqdm(cep_array, desc="Scanning TimeDelay vs. CEP..."):
    lockin.set_dc(8,cep)
    power = pm.read_power()
    cep_bias = float(cep)
    run_timedelay(exp_folder=experiment_folder, tdms_params={"Insertion":insertion, "Power":power, "CEP":cep_bias})

# %% Experiment 8 - PC vs CEP @ Optimum Insertion
"""
Set Optimum Insertion/Max power
Change CEP -> Takes TD
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""
experiment_folder = f'0813_DevicevsCEP'
exp8_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp8_save_path):
    os.makedirs(exp8_save_path)
pc = []
insertion = 7
cep_array = np.arange(0,6.1,0.05)
filename = r'pcvcep.txt'
for cep in tqdm(cep_array, desc="Scanning PC vs. CEP..."):
    lockin.set_dc(8,cep)
    time.sleep(0.5)
    pc.append(lockin.get_lockin(3, 'Mean'))
    # pc.append(pm.read_power())

file_path = os.path.join(exp8_save_path, filename)
combined_array = np.column_stack((cep_array, pc))
np.savetxt(file_path, combined_array, delimiter='\t', header='CEP Bias (V),Photocurrent (A)')
plt.plot(cep_array, pc)
plt.show()

# %% Experiment 9 - TimeDelay vs BG @ Optimum Insertion
"""
Set Optimum Insertion/Max power
Change Backgate -> Takes TD
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""

# define a function to sweep the backgate gracefully
sweep_rate = 30 # seconds per volt
bg_channel = 6
def set_backgate(target, rate=sweep_rate):
    current_bg = lockin.get_ao(bg_channel)[bg_channel-1]['Y'][0]
    duration = abs(target - current_bg)*rate
    print(f"Sweeping backgate from {current_bg} to {target} V...")
    lockin.sweep1d(bg_channel, float(current_bg), float(target), float(duration), 3)
    print(f"Backgate set to {target} V. Running delay scan...")

optimum_insertion = 20
dscan.set_insertion(optimum_insertion)

bg_array = np.arange(-9, 11, 1)
experiment_folder = '13 - 20250606_TDvBackgate_20mmInsertion'
for bg in tqdm(bg_array, desc="Scanning TimeDelay vs. Backgate..."):
    set_backgate(bg)
    bg = float(bg)
    run_timedelay(exp_folder=experiment_folder, tdms_params={"Insertion":optimum_insertion, "BG":bg})


# %% Experiment 10 - TimeDelay vs SD Bias @ Optimum Insertion
"""
Set Optimum Insertion/Max power
Change SD Bias -> Takes TD
(Make sure the call_timedelay.vi is open and TimeDelay VI is configured)
"""
Iplus_channel = 1

optimum_insertion = 45
dscan.set_insertion(optimum_insertion)

sd_array = np.arange(-0.1, 0.1, 0.005)
experiment_folder = '40 - 20250716_TDvSDBias_45mmInsertion_110K_Fine_-100m to 100m Bias_5mSteps'
for sd in tqdm(sd_array, desc="Scanning TimeDelay vs. SD Bias..."):
    lockin.set_dc(Iplus_channel,sd)
    sd = float(sd)
    run_timedelay(exp_folder=experiment_folder, tdms_params={"Insertion":optimum_insertion, "SD":sd})


# %% Experiment 11 - IV vs BG 
"""
Change Backgate -> Takes IV
(Make sure the Lockin_sweep VI is configured)
"""

# define a function to sweep the backgate gracefully
sweep_rate = 30 # seconds per volt
bg_channel = 6
def set_backgate(target, rate=sweep_rate):
    current_bg = lockin.get_ao(bg_channel)[bg_channel-1]['Y'][0]
    duration = abs(target - current_bg)*rate
    print(f"Sweeping backgate from {current_bg} to {target} V...")
    lockin.sweep1d(bg_channel, float(current_bg), float(target), float(duration), 3)
    print(f"Backgate set to {target} V. Running delay scan...")

# First going negative
bg_array = np.arange(0, -35, -0.5)
experiment_folder = '06 - 20250729_IVvsBG\goingNeg'
for bg in tqdm(bg_array, desc="Scanning IV vs. Backgate..."):
    set_backgate(bg)
    bg = float(bg)
    lv.callTransport("Lockin_sweep",experiment_folder,"T=6K, No light", tdms_params={"BG":bg})

# Then going back positive
bg_array = np.arange(-30, 35, 0.5)
experiment_folder = '06 - 20250729_IVvsBG\goingPos'
for bg in tqdm(bg_array, desc="Scanning IV vs. Backgate..."):
    set_backgate(bg)
    bg = float(bg)
    lv.callTransport("Lockin_sweep",experiment_folder,"T=6K, No light", tdms_params={"BG":bg})

# %% Experiment 11 - PCvIns vs BG 
"""
Change Backgate -> Takes PCvIns Scan
"""

# define a function to sweep the backgate gracefully
sweep_rate = 30 # seconds per volt
bg_channel = 6
def set_backgate(target, rate=sweep_rate):
    current_bg = lockin.get_ao(bg_channel)[bg_channel-1]['Y'][0]
    duration = abs(target - current_bg)*rate
    print(f"Sweeping backgate from {current_bg} to {target} V...")
    lockin.sweep1d(bg_channel, float(current_bg), float(target), float(duration), 3)
    print(f"Backgate set to {target} V. Running delay scan...")

# First going negative
bg_array = np.arange(2, 30, 1)
experiment_folder = '14 - 20250805_PCvInsvBG'
exp_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp_save_path):
    os.makedirs(exp_save_path)
for bg in tqdm(bg_array, desc="Scanning PCvIns vs. Backgate..."):
    set_backgate(bg)
    bg = float(bg)

    ins_a, pv_a = insertion_sweep(start=30, stop=50, step=0.2, file_suffix=f"30mBias_{bg}VBG", lockin_measure_channel=3, save_path=exp_save_path)

    plt.plot(ins_a, pv_a)
    plt.xlabel('Insertion (mm)')
    plt.ylabel('Photocurrent (A)')
    plt.show()


# %% - Close Insruments
lockin.close()
kh.close()
transport.close()
dscan.disconnect()
ophir.disconnect()
newfocus.close()
print("Instruments closed.")    


#%% Experiment - Power vs. PC vs. Insertion
"""
Rotates Poalrizer -> Takes PC vs. Insertion Data
"""

experiment_folder = '08 - PCvIns_PowerTest_6K_10mVBias'
exp_save_path = os.path.join(device_folder, experiment_folder)
if not os.path.exists(exp_save_path):
    os.makedirs(exp_save_path)

power_array = np.arange(0.0001, 0.0005, 0.0001)
for value in power_array:
    nf.move_until_power(value,pm,200)
    file_suffix = f"Power={pm.read_power()}"
    insertion, pc = insertion_sweep(start=25, stop=50, step=0.1, file_suffix=file_suffix, lockin_measure_channel=3, save_path=exp_save_path)
    plt.plot(insertion, pc)
    plt.xlabel('Insertion (mm)')
    plt.ylabel('Photocurrent (A)')
    print(f'Plot for: {value}')
    plt.show()


    #%% [markdown]

    """
    ## Running Power vs. PC vs. Insertion.  
    One arm (side arm) is closed.\
    Starting power (max) 0.5 mW.\
    Config: HWP (22.5deg) (Vertial) -> Rotating Pol -> Vertical Pol.\
    Running slow insertion scans: 0 to 90mm 5sec wait.
    """
# %%
