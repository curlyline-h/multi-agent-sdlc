"""
Database Engineer Agent — Postgres Tools

These tools interact with the physical database layer. They will eventually
be wired to a PostgreSQL MCP server and a local Filesystem MCP server.
"""
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from agents.src.shared.tools import tool
import os
from pathlib import Path
from agents.src.shared.llm import get_llm
from langchain_core.prompts import PromptTemplate
import re

# Re-export the generic terminal tool so it can be imported from this package
from agents.src.shared.tools import run_terminal_command  # noqa: F401

# Default root connection
DEFAULT_DB_USER = os.getenv("DB_USER", "postgres")
DEFAULT_DB_PASS = os.getenv("DB_PASS", "postgres")
DEFAULT_DB_HOST = os.getenv("DB_HOST", "localhost")
DEFAULT_DB_PORT = os.getenv("DB_PORT", "5432")

@tool
def create_project_database(project_name: str) -> str:
    """
    Connects to the root PostgreSQL server and executes `CREATE DATABASE <project_name>`.
    Returns the connection string for the new isolated database.
    """
    # Sanitize project name
    safe_name = "".join(c for c in project_name if c.isalnum() or c == "_").lower()
    if not safe_name:
        safe_name = "default_project"
        
    try:
        conn = psycopg2.connect(
            dbname="postgres",
            user=DEFAULT_DB_USER,
            password=DEFAULT_DB_PASS,
            host=DEFAULT_DB_HOST,
            port=DEFAULT_DB_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            # Check if exists and drop if it does to start fresh
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (safe_name,))
            if cur.fetchone():
                cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(safe_name)))
            
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(safe_name)))
        conn.close()
        
        return f"postgresql://{DEFAULT_DB_USER}:{DEFAULT_DB_PASS}@{DEFAULT_DB_HOST}:{DEFAULT_DB_PORT}/{safe_name}"
    except Exception as e:
        raise RuntimeError(f"Failed to create database '{safe_name}': {e}")

@tool
def run_migrations(connection_string: str, tech_stack_hint: str = "sql") -> str:
    """
    Executes the migration scripts. For MVP, we look for SQL files in output/db/ 
    and execute them directly.
    """
    db_dir = Path(__file__).resolve().parents[5] / "output" / "db"
    
    if not db_dir.exists():
        raise RuntimeError(f"No {db_dir} directory found. Cannot run migrations.")
        
    sql_files = list(db_dir.glob("*.sql"))
    if not sql_files:
        raise RuntimeError(f"No .sql files found in {db_dir} directory.")
        
    logs = []
    try:
        conn = psycopg2.connect(connection_string)
        conn.autocommit = True
        with conn.cursor() as cur:
            for file_path in sql_files:
                script = file_path.read_text(encoding="utf-8")
                try:
                    cur.execute(script)
                    logs.append(f"SUCCESS: Executed {file_path.name}")
                except Exception as ex:
                    logs.append(f"ERROR in {file_path.name}: {ex}")
                    raise RuntimeError("\n".join(logs))
        conn.close()
        return "\n".join(logs)
    except Exception as e:
        raise RuntimeError(f"Migration Execution Failed:\n{e}")

@tool
def validate_schema_diff(connection_string: str, design_markdown: str) -> str:
    """
    Connects to the migrated database, extracts its physical schema
    and uses an LLM to compare it against the Architect's markdown design.
    """
    try:
        conn = psycopg2.connect(connection_string)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position;
            """)
            rows = cur.fetchall()
            
            # Format schema dump
            schema_dump = []
            current_table = None
            for table_name, column_name, data_type, is_nullable in rows:
                if table_name != current_table:
                    schema_dump.append(f"\nTABLE {table_name}:")
                    current_table = table_name
                schema_dump.append(f"  - {column_name} ({data_type}, {'NULL' if is_nullable == 'YES' else 'NOT NULL'})")
                
            db_schema_text = "\n".join(schema_dump) if schema_dump else "EMPTY SCHEMA"
        conn.close()
        
        # Use LLM to validate
        prompt = PromptTemplate.from_template("""
    You are a Database Architect.
    
    Required Design:
    {design_markdown}
    
    Actual Database Schema (extracted from DB):
    {db_schema_text}
    
    Instruction:
    Compare the Actual Database Schema against the Required Design. 
    If the Actual Database Schema implements all tables and fields required by the design, output exactly: SCHEMA_MATCH
    If there are missing tables, incorrect types, or missing columns, list the exact SQL fixes needed to correct it.
    """)
    
        llm = get_llm(temperature=0.1, max_tokens=4000)
        formatted_prompt = prompt.format(design_markdown=design_markdown, db_schema_text=db_schema_text)
        response = llm.invoke(formatted_prompt)
        content = response.content.strip()
    
        # Strip <think> blocks so we don't pollute the context window on loop
        clean_content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    
        return clean_content
    except Exception as e:
        return f"Schema Validation Error: {e}"
