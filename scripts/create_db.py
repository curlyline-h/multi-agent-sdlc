import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def create_postgresql_database(db_name: str):
    # 1. Connect to the default 'postgres' management database
    conn = psycopg2.connect(
        host="localhost",
        user="postgres",
        password="postgres",  # Replace with your actual admin password
        port="5432",
        database="postgres"      # Crucial: Must connect here first
    )
    
    # 2. Enable autocommit (PostgreSQL forbids creating databases inside transactions)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    
    cursor = conn.cursor()
    
    try:
        # 3. Safely check if the target database already exists
        cursor.execute(f"SELECT 1 FROM pg_catalog.pg_database WHERE datname = '{db_name}';")
        exists = cursor.fetchone()
        
        if not exists:
            # 4. Execute the raw SQL command to build the database
            cursor.execute(f"CREATE DATABASE {db_name};")
            print(f"Database '{db_name}' created successfully!")
        else:
            print(f"Database '{db_name}' already exists.")
            
    except Exception as e:
        print(f"An error occurred: {e}")
        
    finally:
        # 5. Clean up connection pools
        cursor.close()
        conn.close()

# Run the function with your target database name
if __name__ == "__main__":
    create_postgresql_database("AgenticDB")
