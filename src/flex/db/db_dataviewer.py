import pandas as pd
import matplotlib.pyplot as plt
from flex.db import FLEXDB
import numpy as np

def extract_sweep(params):
    db = FLEXDB('levylab', 'llab_reader')
    sql_query = """
        SELECT time, i001, i002, d000, d001 
        FROM llab_076
        WHERE b000 = TRUE
        AND i001 = %s
        AND i002 = %s
        AND time BETWEEN %s AND %s
        ORDER BY time ASC
    """
    
    results = db.execute_fetch(sql_query, params=params, method='all')
    
    df = pd.DataFrame(results)
    
    return df[0], df[3]

def plot_sweep1d(time_range, sweep_config, serial):
    db = FLEXDB('levylab', 'llab_admin')
    sweep_channel = sweep_config.get("sweep_channel")
    measure_channel = sweep_config.get("measure_channel")
    ref_channel = sweep_config.get("ref_channel")
# TODO: Should optimize the query with an Inner Join
    sql_query_X = """
        SELECT time, i001, i002, d000, d001 
        FROM llab_076
        WHERE b000 = TRUE
        AND i001 = %s
        AND i002 = %s
        AND time BETWEEN %s AND %s
    """
    sql_query_X_params = (measure_channel, ref_channel, time_range[0], time_range[1])

    sql_query_AO = """
        SELECT time, i001, d001
        FROM llab_078
        WHERE b000 = TRUE
        AND i001 = %s
        AND time BETWEEN %s AND %s
    """
    sql_query_AO_params = (sweep_channel, time_range[0], time_range[1])
    results_X = db.execute_fetch(sql_query_X, params=sql_query_X_params, method='all')
    results_AO = db.execute_fetch(sql_query_AO, params=sql_query_AO_params, method='all')

    db.close_connection()
    df_X = pd.DataFrame(results_X)
    df_AO = pd.DataFrame(results_AO)
 

    plt.plot(df_AO[2], df_X[3])
    plt.xlabel('Sweep Voltage (V)')
    plt.ylabel('Lockin X data (V)')
    plt.tight_layout()
    plt.show()
    
'''
NOTE: Instrument serials should be extracted from the instrument via IDN
This will help in dataviewing'''


if __name__ == "__main__":
    params = ('1', '1', '2025-04-04 14:49:15-0400', '2025-04-04 14:49:25-0400')
    time, lockin_x_data = extract_sweep(params)

    plt.plot(time, lockin_x_data)
    plt.xlabel('Time') 
    plt.ylabel('Lockin X Data') 
    plt.xticks(rotation=45) 
    plt.tight_layout()
    plt.show()

