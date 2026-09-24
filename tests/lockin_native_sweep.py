#%%
from flex.tdms import flexTDMS as fs
from flex.exp.CESession import CESession
import time
from pathlib import Path


exp = CESession()
save_dir = exp.get_device_path() / 'IV_Sweeps'
device = 'SA40690H.20260923'

lockin = exp.DAQ
ppms = exp.Temperature

sweep_config = {
    "Sweep Time (s)": 5,
    "Initial Wait (s)": 2,
    "Return to Start": False,
    "Channels": [{
        "Enable?": True,
        "Channel": 5,
        "Start": 0,
        "End": 0.1,
        "Pattern": "Table",
        "Table": [0, 0.1]
    }]
}

def iv_sweep(save_path, sweep_config, max_attempts=3):
    """
    Performs an IV sweep with built-in retry logic if it fails to start.
    """
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    attempt = 1
    while attempt <= max_attempts:
        print(f"--- IV Sweep: Attempt {attempt} of {max_attempts} ---")
        
        try:
            # Trigger the sweep
            lockin.lockin_sweep(sweep_config=sweep_config)
            
            # Check state
            state = lockin.getState()
            if state == 'started':
                print("Sweep ended successfully. Saving data...")
                fs.write_acquisition_tdms(
                    str(save_path),
                    lockin.getSweepWaveforms(),
                    properties={
                        "Author": "Ahmed Omran",
                        "Description": "IV sweep",
                    },
                    Magnet=ppms.getMagnet()['field'],
                )
                print("Sweep and save completed successfully!")
                return True  # Exit function entirely on success
            
            else:
                print(f"Warning: Sweep failed.")
                lockin.setState('start')
                lockin.setState('stop sweep')
                
        except Exception as e:
            print(f"An error occurred during the sweep: {e}")
        
        # If it fails, prepare to retry
        attempt += 1
        if attempt <= max_attempts:
            print("Retrying sweep in 2 seconds...\n")
            time.sleep(2)
        else:
            print("Error: Max retry attempts reached. IV sweep failed permanently.")
            return False

for _ in range(3):
    next_index = len(list(save_dir.glob(f"{device}.*.tdms")))
    save_path = save_dir / f"{device}.{next_index:06d}.tdms"
    iv_sweep(save_path, sweep_config)

# %%
