import pandas as pd
import matplotlib.pyplot as plt
from flex.db import FLEXDB

def extract_sweep(time_range, measure_channel, ref_channel):
    db = FLEXDB('levylab', 'llab_reader')
    sql_query = """
        SELECT time, i001, i002, d000, d001 
        FROM llab_076
        WHERE b000 = TRUE
        AND time BETWEEN %s AND %s
    """
    
    results = db.execute_fetch(sql_query, params=time_range, method='all')
    
    df = pd.DataFrame(results)
    filtered_df = df[(df[1] == measure_channel) & (df[2] == ref_channel)]
    
    return filtered_df[0], filtered_df[3]

def plot_sweep1d(time_range, sweep_config):
    db = FLEXDB('levylab', 'llab_reader')
    measure_channel = sweep_config.get("measure_channel")
    ref_channel = sweep_config.get("ref_channel")

    sql_query = """
        SELECT time, i001, i002, d000, d001 
        FROM llab_076
        WHERE b000 = TRUE
        AND time BETWEEN %s AND %s
    """
    
    results = db.execute_fetch(sql_query, params=time_range, method='all')
    
    df = pd.DataFrame(results)
    filtered_df = df[(df[1] == measure_channel) & (df[2] == ref_channel)]

    plt.plot(filtered_df[0], filtered_df[3])
    plt.xlabel('Time')
    plt.ylabel('Lockin X Data')
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show()
    
'''
NOTE: Instrument serials should be extracted from the instrument
This will help in dataviewing'''

# time_range = ('2025-04-03 13:22:00-0400', 
#               '2025-04-03 13:24:00-0400')
# time, lockin_x_data = extract_sweep(time_range, measure_channel=1, ref_channel=1)

# plt.plot(time, lockin_x_data)
# plt.xlabel('Time') 
# plt.ylabel('Lockin X Data') 
# plt.xticks(rotation=45) 
# plt.tight_layout()
# plt.show()