# %% - Import needed modules
import pandas as pd
import matplotlib.pyplot as plt
from flex.db import FLEXDB

# %% - Connect to the database
def connect_db(dbname="levylab", username="llab_admin"):
    """Create a connection to the database"""
    db = FLEXDB(dbname=dbname, username=username)
    print(f"Connected to database: {dbname}")
    return db

# %% - List all tables in database
def list_tables(db):
    """List all tables in the database"""
    sql = """
    SELECT table_name 
    FROM information_schema.tables
    WHERE table_schema = 'public'
    AND table_name LIKE 'llab_%'
    ORDER BY table_name;
    """
    tables = db.execute_fetch(sql, method='all')
    print(f"Found {len(tables)} tables")
    return [t[0] for t in tables]

# %% - Get table structure
def get_table_structure(db, table_name):
    """Get the structure of a table"""
    sql = f"""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = '{table_name}'
    ORDER BY ordinal_position;
    """
    columns = db.execute_fetch(sql, method='all')
    return pd.DataFrame(columns, columns=['Column', 'Type'])

# %% - Find tables with specific column names
def find_tables_with_columns(db, keywords):
    """Find tables that have columns containing any of the keywords"""
    results = []
    
    for keyword in keywords:
        sql = f"""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE column_name LIKE '%{keyword}%'
        AND table_schema = 'public'
        AND table_name LIKE 'llab_%'
        ORDER BY table_name;
        """
        matches = db.execute_fetch(sql, method='all')
        for match in matches:
            results.append({"table": match[0], "column": match[1], "keyword": keyword})
            
    return pd.DataFrame(results)

# %% - Look for PPMS data - check recent entries
def check_for_ppms_data(db, potential_tables):
    """Sample data from potential PPMS tables"""
    results = {}
    
    for table in potential_tables:
        sql = f"""
        SELECT * FROM {table}
        ORDER BY time DESC
        LIMIT 5;
        """
        try:
            data = db.execute_fetch(sql, method='all')
            if data:
                # Get column names
                col_sql = f"""
                SELECT column_name 
                FROM information_schema.columns
                WHERE table_name = '{table}'
                ORDER BY ordinal_position;
                """
                columns = [col[0] for col in db.execute_fetch(col_sql, method='all')]
                
                # Convert to DataFrame for better display
                results[table] = pd.DataFrame(data, columns=columns)
        except Exception as e:
            print(f"Error querying table {table}: {e}")
            
    return results

# %% - Main execution - uncomment sections as needed
if __name__ == "__main__":
    # Connect to the database
    db = connect_db()
    
    # List all tables
    tables = list_tables(db)
    print(f"Tables: {tables[:10]}...")
    
    # Search for potential PPMS-related tables
    ppms_keywords = ['temp', 'temperature', 'magnet', 'field', 'ppms', 'cryo']
    potential_ppms_tables = find_tables_with_columns(db, ppms_keywords)
    print("Potential PPMS-related tables:")
    print(potential_ppms_tables)
    
    # Uncomment to examine the structure of specific tables
    # for table in potential_ppms_tables['table'].unique()[:3]:  # Examine first 3 tables
    #     print(f"\nStructure of {table}:")
    #     print(get_table_structure(db, table))
    
    # Sample data from potential PPMS tables
    # sample_data = check_for_ppms_data(db, potential_ppms_tables['table'].unique())
    # for table, data in sample_data.items():
    #     print(f"\nSample data from {table}:")
    #     print(data)
    
    # Close the connection
    db.close_connection()
    print("Database connection closed")