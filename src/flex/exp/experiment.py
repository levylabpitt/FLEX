import psycopg2
from datetime import datetime

class Experiment:
    def __init__(self, db_config):
        """
        Initialize the Experiment class with database configuration.

        :param db_config: A dictionary containing database connection details (dbname, user, password, host, port).
        """
        self.db_config = db_config
        self.connection = psycopg2.connect(**db_config)
        self.create_table()

    def create_table(self):
        """
        Create the experiments table if it doesn't already exist.
        """
        query = """
        CREATE TABLE IF NOT EXISTS experiments (
            id SERIAL PRIMARY KEY,
            user_name VARCHAR(255) NOT NULL,
            experiment_name VARCHAR(255) NOT NULL,
            description TEXT,
            start_time TIMESTAMP NOT NULL,
            end_time TIMESTAMP
        );
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query)
            self.connection.commit()

    def start_experiment(self, user_name, experiment_name, description):
        """
        Start a new experiment instance.

        :param user_name: Name of the user.
        :param experiment_name: Name of the experiment.
        :param description: Description of the experiment.
        """
        start_time = datetime.now()
        query = """
        INSERT INTO experiments (user_name, experiment_name, description, start_time)
        VALUES (%s, %s, %s, %s)
        RETURNING id;
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (user_name, experiment_name, description, start_time))
            experiment_id = cursor.fetchone()[0]
            self.connection.commit()
        return experiment_id

    def end_experiment(self, experiment_id):
        """
        End an experiment instance by recording the end time.

        :param experiment_id: ID of the experiment to end.
        """
        end_time = datetime.now()
        query = """
        UPDATE experiments
        SET end_time = %s
        WHERE id = %s;
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (end_time, experiment_id))
            self.connection.commit()

    def get_experiment_by_name(self, experiment_name):
        """
        Retrieve experiments by name.

        :param experiment_name: Name of the experiment.
        """
        query = """
        SELECT * FROM experiments WHERE experiment_name = %s;
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (experiment_name,))
            results = cursor.fetchall()
        return results

    def get_experiments_by_time_range(self, start_time, end_time):
        """
        Retrieve experiments within a specific time range.

        :param start_time: Start of the time range (datetime).
        :param end_time: End of the time range (datetime).
        """
        query = """
        SELECT * FROM experiments
        WHERE start_time >= %s AND end_time <= %s;
        """
        with self.connection.cursor() as cursor:
            cursor.execute(query, (start_time, end_time))
            results = cursor.fetchall()
        return results

    def close(self):
        """
        Close the database connection.
        """
        self.connection.close()


if __name__ == "__main__":
    db_config = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': 'flex',
    'host': '10.226.177.185',
    'port': 5433
}