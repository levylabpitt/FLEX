# flex/logger.py
from datetime import datetime
from IPython import get_ipython

class CellLogger:
    def __init__(self, experiment):
        self.experiment = experiment
        self.shell = get_ipython()
        self.cell_counter = 1  # Start at 1
        self.shell.events.register('post_run_cell', self._log_cell)

    def _log_cell(self, result):
        cell_code = result.info.raw_cell

        sql = """
            INSERT INTO cell_log (timestamp, experiment_id, cell_id, cell_content)
            VALUES (%s, %s, %s, %s)
        """
        self.experiment.db.execute_fetch(
            sql_string=sql,
            params=(datetime.now(), str(self.experiment.session_id),
                    self.cell_counter, cell_code),
            method='none'
        )

        print(f"[LOG] Cell #{self.cell_counter} saved to DB.")
        self.cell_counter += 1

    def unregister(self):
        if self.shell:
            self.shell.events.unregister('post_run_cell', self._log_cell)
