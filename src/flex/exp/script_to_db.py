from IPython import get_ipython
from datetime import datetime
import psycopg2

# Database connection settings
DB_CONFIG = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': 'flex',
    'host': '10.226.177.185',
    'port': 5433
}

# Global variable to store the active experiment ID
active_experiment_id = None

def log_executed_cell_to_db(result):
    """
    Log the executed cell content to the database.
    :param result: The execution result object from IPython.
    """
    global active_experiment_id
    if active_experiment_id is None:
        print("No active experiment ID. Please set an active experiment first.")
        return

    # Get the raw content of the executed cell
    cell_content = result.info.raw_cell.strip()

    # Skip logging if the cell is empty or part of a background process
    if not cell_content or "__jupyter_exec_background__" in cell_content:
        return

    # Get the current time
    execution_time = datetime.now()

    # Define the query to log the executed cell to the experiment_scripts table
    query = """
    INSERT INTO experiment_scripts (experiment_id, script_content, execution_time)
    VALUES (%s, %s, %s);
    """

    try:
        # Connect to the database
        connection = psycopg2.connect(**DB_CONFIG)
        with connection.cursor() as cursor:
            cursor.execute(query, (active_experiment_id, cell_content, execution_time))
            connection.commit()
    except Exception as e:
        print(f"Error logging cell to database: {e}")
    finally:
        if connection:
            connection.close()

def set_active_experiment(experiment_id):
    """
    Set the active experiment ID for the session.
    :param experiment_id: The ID of the active experiment.
    """
    global active_experiment_id
    active_experiment_id = experiment_id
    print(f"Active experiment set to ID: {active_experiment_id}")

# Attach the function to IPython's post-run-cell event
ipython = get_ipython()
if ipython:
    ipython.events.register('post_run_cell', log_executed_cell_to_db)

print("Logging of user-executed cell content to the database is now active.")
