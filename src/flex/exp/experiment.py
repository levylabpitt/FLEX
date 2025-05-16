# experiment.py
import uuid
from datetime import datetime
from flex.db import FLEXDB
from  .script_to_db import CellLogger
from IPython import get_ipython
from .users import User
from .dbexptoAsana import trigger_n8n_dbexptoAsana

# TODO: Should load the user updater here

class Experiment:
    def __init__(self, user: User, notes="", enable_cell_log=True):
        # TODO: Add a feature to support collaborators
        # TODO: Add failsafes. If one script fails, the experiment should not be halted.
        # TODO: Should add a logging feature 
        
        # User availability check
        if user not in set(User.__args__): 
            raise ValueError(f"User '{user}' is not registered.")
        if enable_cell_log and get_ipython():
            self.cell_logger = CellLogger(self)
        # Use date and time for session ID
        self.session_id = datetime.now().strftime("%Y%m%d%H%M%S")
        self.user = user
        self.notes = [notes] if notes else [] #TODO: These should be logged to the database
        self.start_time = datetime.now()
        self.end_time = None
        self.instruments = {}

        self.db = FLEXDB(dbname="levylab_test", username='llab_admin')
        print(f"[{self.start_time}] Experiment started: {self.session_id}")
        self._log_start_to_db()
        trigger_n8n_dbexptoAsana()

    def _log_start_to_db(self):
        sql = """
            INSERT INTO exp (id, username, start_time, end_time, instruments)
            VALUES (%s, %s, %s, %s, %s)
        """
        self.db.execute_fetch(
            sql_string=sql,
            params=(str(self.session_id), self.user, self.start_time, None, []),
            method='none'
        )

    def init(self, cls, name=None, *args, **kwargs): 
        #TODO: Databse should be updated whenever a new instrument is added with the serial number
        name = name or cls.__name__
        if name in self.instruments:
            raise ValueError(f"Instrument '{name}' already initialized.")
        self.instruments[name] = cls(*args, **kwargs)
        return self.instruments[name]

    def new_measurement(self, notes=""):
        return Measurement(self, notes=notes)

    def end(self):
        self.end_time = datetime.now()
        self._update_end_time()
        if hasattr(self, "cell_logger"):
            self.cell_logger.unregister()
        self.db.close_connection()
        trigger_n8n_dbexptoAsana()
        print(f"[{self.end_time}] Experiment ended and saved.")

    def _update_end_time(self):
        sql = """
            UPDATE exp SET end_time = %s, instruments = %s
            WHERE id = %s
        """
        self.db.execute_fetch(
            sql_string=sql,
            params=(self.end_time, list(self.instruments.keys()), str(self.session_id)),
            method='none'
        )

    def _log_to_db(self):
        sql = """
            INSERT INTO exp (id, username, start_time, end_time, instruments)
            VALUES (%s, %s, %s, %s, %s)
        """
        self.db.execute_fetch(
            sql_string=sql,
            params=(str(self.session_id), self.user, self.start_time, self.end_time, list(self.instruments.keys())),
            method=None  # no fetch
        )
        print(f"Experiment {self.session_id} logged to DB.")


class Measurement:
    def __init__(self, experiment, notes=""):
        self.experiment = experiment
        self.experiment_id = experiment.session_id
        self.notes = [notes] if notes else []
        self.start_time = None
        self.end_time = None
        # Generate measurement ID using current date and time
        self.measurement_id = datetime.now().strftime("%Y%m%d%H%M%S")

    def __enter__(self):
        self.start_time = datetime.now()
        print(f"[{self.start_time}] Measurement started.")
        return self

    def add_note(self, note):
        self.notes.append(f"{datetime.now().isoformat()}: {note}")
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.end()

    def end(self):
        self.end_time = datetime.now()
        self._log_to_db()
        print(f"[{self.end_time}] Measurement ended and logged.")

    def _log_to_db(self):
        sql = """
            INSERT INTO meas (id, experiment_id, start_time, end_time, notes)
            VALUES (%s, %s, %s, %s, %s)
        """
        self.experiment.db.execute_fetch(
            sql_string=sql,
            params=(str(self.measurement_id), str(self.experiment_id),
                    self.start_time, self.end_time, self.notes),
            method='none'  # no fetch
        )

