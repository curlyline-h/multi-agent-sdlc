import asyncio
import os
import sys

# Ensure the project root is in the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import text
from backend.database import engine

async def run_migration():
    print("Starting manual migration to add current_subgraph_node...")
    async with engine.begin() as conn:
        try:
            # Check if column already exists to prevent crash on re-run
            res = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='workflows' AND column_name='current_subgraph_node';"))
            if res.fetchone():
                print("Column 'current_subgraph_node' already exists.")
            else:
                await conn.execute(text("ALTER TABLE workflows ADD COLUMN current_subgraph_node VARCHAR(100);"))
                print("Successfully added column 'current_subgraph_node' to workflows table.")
        except Exception as e:
            print(f"Migration failed: {e}")

if __name__ == "__main__":
    asyncio.run(run_migration())
