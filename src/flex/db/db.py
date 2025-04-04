import psycopg2
import logging
from contextlib import closing
import os

class FLEXDB:
    """
    Connect to the Levylab database.
    
    Attributes:
        dbname: Database name.
        username: Database username.
        conn: Database connection object.
        cursor: Database cursor object.
    
    Methods:
        __init__(dbname, username): Initialize with dbname and username.
        connect(): Connect to the database.
        close_connection(): Close the connection.
        execute_fetch(sql_string, params=None, method='one', size=5): Execute a SQL query and fetch results.
    """
    def __init__(self, dbname, username):
        self.username = username
        self.dbname = dbname
        self.conn = None
        self.connect()

    def connect(self):
        """Establish a connection to the database."""
        try:
            self.conn = psycopg2.connect(
                dbname=self.dbname,
                user=self.username,
                host='db.levylab.org',
            )
            logging.info(f"Connected to database '{self.dbname}' as user '{self.username}'.")
        except psycopg2.Error as e:
            logging.error(f"Database connection failed: {e}")
            raise

    def close_connection(self):
        """Close the database connection and cursor."""
        if self.conn:
            self.conn.close()
            logging.info("Database connection closed.")

    def execute_fetch(self, sql_string, params=None, method='one', size=5):
        """
        Execute a SQL query and fetch results.
        
        Args:
            sql_string: SQL query string.
            params: Parameters for parameterized queries.
            method: Fetch method ('one', 'many', 'all').
            size: Number of rows to fetch for 'many' method.
        
        Returns:
            Query result(s) based on the fetch method.
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(sql_string, params)
                logging.debug(f"Executed query: {sql_string} with params: {params}")
                
                if method == 'one':
                    return cursor.fetchone()
                elif method == 'many':
                    return cursor.fetchmany(size=size)
                elif method == 'all':
                    return cursor.fetchall()
                else:
                    raise ValueError("Invalid method. Use 'one', 'many', or 'all'.")
        except psycopg2.Error as e:
            logging.error(f"Query execution failed: {e}")
            raise
        finally:
            self.close_connection()

    def list_logged_users(self):
        """
        Retrieve all currently logged-on users.
        
        Returns:
            A list of dictionaries containing user information.
        """
        query = """
        SELECT usename AS username,
               client_addr AS client_address,
               backend_start,
               state
        FROM pg_stat_activity
        WHERE usename IS NOT NULL
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query)
                logging.debug("Retrieved logged-on users.")
                columns = [desc[0] for desc in cursor.description]
                results = cursor.fetchall()
                return [dict(zip(columns, row)) for row in results]
        except psycopg2.Error as e:
            logging.error(f"Failed to retrieve logged-on users: {e}")
            raise
        finally:
            self.close_connection()

    def terminate_connections(self, client_address):
        """
        Terminate all connections from a specific client address.
        
        Args:
            client_address: The IP address of the client to disconnect.
        
        Returns:
            The number of connections terminated.
        """
        query = """
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE client_addr = %s
        AND pid <> pg_backend_pid(); -- Exclude the current session
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(query, (client_address,))
                terminated_connections = cursor.rowcount
                logging.info(f"Terminated {terminated_connections} connections from {client_address}.")
                return terminated_connections
        except psycopg2.Error as e:
            logging.error(f"Failed to terminate connections from {client_address}: {e}")
            raise
        finally:
            self.close_connection()


logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

# Configure logging
logging.basicConfig(
    filename=logpath + '\db.log',
    level=logging.DEBUG,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

if __name__ == "__main__":
    # Example usage of FLEXDB
    try:
        db = FLEXDB("levylab", "llab_admin")
        
        sql_string = """
            SELECT time, d017 FROM llab_011
            WHERE d017 IS NOT NULL
            AND time BETWEEN %s AND %s
        """
        params = ('2024-06-04 21:00:08.638105', '2024-06-04 22:04:23.543921')
        results = db.execute_fetch(sql_string, params=params, method='many', size=5)     
        print(results)
    except Exception as e:
        logging.error(f"An error occurred: {e}")
    # finally:
    #     db.close_connection()