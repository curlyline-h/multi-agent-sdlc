"""
Database Engineer Agent — Node Functions

Flow:
  setup_db → write_migrations → execute_migrations → validate_schema
  → [router loops back to write_migrations if validation fails]
"""
import json
import os
import re
from pathlib import Path
from langchain_core.prompts import PromptTemplate
from agents.src.shared.llm import get_llm, llm_tool_invoke_with_retry
from pydantic import BaseModel, Field
from typing import List

from agents.src.agents.database_engineer.state import DatabaseEngineerState
from typing import Dict, Any
from agents.src.agents.database_engineer.tools import (
    create_project_database,
    run_migrations,
    validate_schema_diff,
    run_terminal_command,       
)
from agents.src.shared.tools import (
    semantic_code_search,
    read_file_range,
    replace_file_content,
    list_directory,
    fetch_server_logs,
    search_web,
    rag_search,
)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts"
_ROOT_DIR = Path(__file__).resolve().parents[4]

# ---------------------------------------------------------------------------
# LLM setup
# ---------------------------------------------------------------------------
_llm = get_llm(temperature=0.1, max_tokens=4000)


def _get_design_doc(state: DatabaseEngineerState) -> str:
    design_doc = state.final_design_doc or ""
    if len(design_doc.strip()) < 50:
        print("DB Engineer: State design doc is empty. Attempting to load from schema_approval file...")
        try:
            import glob
            approval_files = glob.glob(str(_ROOT_DIR / "schema_approval*.md"))
            if approval_files:
                approval_files.sort(key=os.path.getmtime, reverse=True)
                with open(approval_files[0], "r", encoding="utf-8") as f:
                    design_doc = f.read()
                print(f"DB Engineer: Successfully loaded design doc ({len(design_doc)} chars) from {approval_files[0]}")
        except Exception as e:
            print(f"DB Engineer: Failed to load from file: {e}")
    return design_doc

_CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"`]?(\w+)[\"`]?[^;]*;", re.IGNORECASE | re.DOTALL)


def _merge_sql(old: str, new: str) -> str:
    """Keeps previously-defined tables when a later DB task rewrites init.sql."""
    new_tables = {m.group(1).lower() for m in _CREATE_RE.finditer(new)}
    missing = [m.group(0) for m in _CREATE_RE.finditer(old) if m.group(1).lower() not in new_tables]
    if not missing:
        return new
    print(f"DB Engineer: preserving {len(missing)} previously defined table(s) in db/init.sql")
    return new.rstrip() + "\n\n" + "\n\n".join(missing) + "\n"


def _is_db_required(design_doc: str) -> bool:
    if len(design_doc.strip()) < 50:
        return True # Default to true if missing
    design_lower = design_doc.lower()
    if "create table" in design_lower or "postgresql" in design_lower or "postgres" in design_lower:
        return True
    no_db_signals = [
        "no database is required", "database: none", "browser game",
        "client-side only", "client side only", "static site"
    ]
    if any(signal in design_lower for signal in no_db_signals):
        return False
    return True

# ---------------------------------------------------------------------------
# 1. Setup DB Node
# ---------------------------------------------------------------------------
def setup_db_node(state: DatabaseEngineerState) -> dict:
    """
    Creates the isolated PostgreSQL database for this project.
    """
    design_doc = _get_design_doc(state)
    if not _is_db_required(design_doc):
        print("DB Engineer: Skipping database setup (no DB required).")
        return {"db_connection_string": "Skipped: No DB required"}

    try:
        conn_string = create_project_database.invoke({"project_name": state.project_name})
    except Exception as e:
        conn_string = f"Failed to create DB: {e}"
        print(conn_string)
        
    return {"db_connection_string": conn_string}


from pydantic import BaseModel, Field
from typing import List

class GeneratedFile(BaseModel):
    path: str = Field(description="The relative path to save the file to, e.g. output/db/init.sql")
    content: str = Field(description="The full raw code content of the file")

class CodeGenerationResponse(BaseModel):
    files: List[GeneratedFile] = Field(description="List of files to generate or update")

def _get_codebase_summary() -> str:
    from agents.src.shared.tools import get_output_dir
    output_dir = get_output_dir() / "db"
    if not output_dir.exists():
        return "No generated database scripts found yet."
        
    code_blocks = []
    allowed_extensions = {".sql", ".prisma", ".json", ".md"}
    
    for path in sorted(output_dir.rglob("*")):
        if path.is_file():
            if path.suffix in allowed_extensions:
                try:
                    rel_path = path.relative_to(_ROOT_DIR)
                    content = path.read_text(encoding="utf-8")
                    if len(content) > 10000:
                        content = content[:10000] + "\n... [TRUNCATED] ..."
                    block = f"File: {rel_path}\n```sql\n{content}\n```"
                    code_blocks.append(block)
                except Exception as e:
                    code_blocks.append(f"File: {path.name} (Error: {e})")
                    
    if not code_blocks:
        return "No files generated yet."
        
    return "\n\n".join(code_blocks)

# ---------------------------------------------------------------------------
# 2. Write Migrations Node
# ---------------------------------------------------------------------------
def write_migrations_node(state: DatabaseEngineerState) -> dict:
    """
    Translates the Architect's design document into raw database schema definitions.
    If the design specifies no database is needed, writes a README and skips.
    """
    design_doc = _get_design_doc(state)
    
    if len(design_doc.strip()) < 50:
        raise ValueError("System Design Document is empty or missing! DB Engineer cannot proceed without a design doc.")
        
    if not _is_db_required(design_doc):
        from agents.src.shared.tools import get_output_dir
        readme_path = get_output_dir() / "db" / "README.md"
        readme_path.parent.mkdir(parents=True, exist_ok=True)
        readme_path.write_text(
            "# Database\n\nNo database is required for this project.\n\n"
            "The System Design specifies that data is managed in-memory, via localStorage, "
            "or through file-based storage. No SQL schema or migrations are needed.\n",
            encoding="utf-8"
        )
        print("DB Engineer: No database needed for this project. Skipping SQL generation.")
        return {"migration_logs": "Skipped: No database required for this project type."}

    from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
    import re
    import json
    
    prompt_path = _PROMPTS_DIR / "database_engineer.txt"
    prompt = PromptTemplate.from_template(prompt_path.read_text(encoding="utf-8"))
    
    existing_code = _get_codebase_summary()
    
    formatted = prompt.format(
        design_doc=state.final_design_doc,
        existing_code=existing_code,
        logs=state.migration_logs or "None.",
        diff=state.schema_diff_notes or "None."
    )
    
    _ct = state.current_task if isinstance(state.current_task, dict) else {}
    if _ct:
        formatted += (
            f"\n\nCurrent DB task: {_ct.get('title','')} - {_ct.get('description','')}\n"
            "If db/init.sql already exists above, output the COMPLETE merged db/init.sql containing ALL existing tables plus the new/changed ones. "
            "NEVER drop or replace existing domain tables, and never introduce entities that are not in the PRD/design (e.g. generic users/posts/comments)."
        )
    formatted += "\n\nCRITICAL: You MUST output ONLY valid JSON matching this schema:\n{\n  \"files\": [\n    {\"path\": \"output/db/init.sql\", \"content\": \"raw code\"}\n  ]\n}\n\nNote: You have FULL terminal and file system access. You can call `run_terminal_command`, `semantic_code_search`, `read_file_range`, `replace_file_content`, `list_directory`, `fetch_server_logs`, `search_web`, and `rag_search` to inspect the workspace or look up documentation. Gather whatever context you need first. Once ready, output your final payload wrapped EXACTLY in a ```json block matching the CodeGenerationResponse schema. DO NOT output anything else after the JSON block."
    
    import os
    if os.name == 'nt':
        formatted += "\n\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p`, `rm -rf`, or `touch`. Use Windows equivalents (e.g., `mkdir` without `-p` to create directories, `del /s /q` or `rmdir /s /q` for deletion). `mkdir` automatically creates intermediate directories in cmd."
        
    from agents.src.shared.tools import write_file, get_output_dir
    tools_list = [write_file, run_terminal_command, semantic_code_search, read_file_range, replace_file_content, list_directory, fetch_server_logs, search_web, rag_search, create_project_database, run_migrations, validate_schema_diff]
    llm_with_tools = _llm.bind_tools(tools_list)
    
    messages = [
        SystemMessage(content="You are a Principal Database Engineer. You write sql migrations."),
        HumanMessage(content=formatted)
    ]
    
    # ReAct Loop
    turn_limit = 15
    for turn in range(turn_limit):
        try:
            response = llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name="Database Engineer")
        except Exception as e:
            if "tool_calls" in str(e).lower() or "invalid_json" in str(e).lower():
                import ast
                error_str = str(e)
                start_idx = error_str.find("'{")
                end_idx = error_str.rfind("}'") + 2
                if start_idx != -1 and end_idx != -1:
                    if end_idx == -1 or end_idx <= start_idx:
                        end_idx = error_str.rfind("'")
                    try:
                        raw_fg = error_str[start_idx:end_idx].replace("\\n", "\n").replace("\\'", "'")
                        failed_gen = json.loads(raw_fg, strict=False)
                        args = failed_gen.get("arguments", {})
                        class DummyResponse:
                            content = json.dumps(args) if isinstance(args, dict) else str(args)
                            tool_calls = []
                        response = DummyResponse()
                    except Exception:
                        raise e
                else:
                    raise e
            else:
                raise e
                
        messages.append(response)
        
        if not getattr(response, "tool_calls", []):
            break
            
        # Check if it accidentally provided the JSON block alongside tool calls
        if response.content and "```json" in response.content:
            break
            
        tool_map = {tool.name: tool for tool in tools_list}
        for tool_call in response.tool_calls:
            name = tool_call["name"]
            print(f"Agent calling tool: {name} with args {tool_call['args']}")
            if name in tool_map:
                result = tool_map[name].invoke(tool_call["args"])
            else:
                result = f"Error: Tool {name} not found."
            messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

    try:
        # Find the content containing the JSON (only from assistant responses in messages[2:])
        content = ""
        for msg in reversed(messages[2:]):
            if hasattr(msg, "content") and isinstance(msg.content, str) and ("```json" in msg.content or '"files"' in msg.content):
                content = msg.content
                break
        if not content and len(messages) > 2:
            last_ai = next((m for m in reversed(messages[2:]) if getattr(m, "type", "ai") == "ai" and getattr(m, "content", "")), None)
            content = last_ai.content if last_ai else ""
            
        from agents.src.shared.llm import extract_files_and_commands_robust
        from agents.src.shared.tools import get_output_dir, _clean_rel_path
        output_dir = get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)

        parsed = extract_files_and_commands_robust(content)
        files_written = 0
        for f in parsed.get("files", []):
            fpath = f.get("path") if isinstance(f, dict) else getattr(f, "path", "")
            fcontent = f.get("content") if isinstance(f, dict) else getattr(f, "content", "")
            if fpath and fcontent and fcontent.strip() not in ("raw code", "...") and len(fcontent.strip()) > 20:
                clean_path = _clean_rel_path(fpath)
                file_path = output_dir / clean_path
                file_path.parent.mkdir(parents=True, exist_ok=True)
                if file_path.name == "init.sql" and file_path.exists():
                    fcontent = _merge_sql(file_path.read_text(encoding="utf-8", errors="replace"), fcontent)
                file_path.write_text(fcontent, encoding="utf-8")
                files_written += 1
                print(f"DB Engineer wrote: {fpath}")

        # Fallback: if no valid SQL DDL file was written yet, extract ```sql blocks or invoke tool-free DDL generation
        init_sql_path = output_dir / "db" / "init.sql"
        existing_sql = init_sql_path.read_text(encoding="utf-8", errors="replace") if init_sql_path.exists() else ""
        if "CREATE TABLE" not in existing_sql.upper():
            sql_blocks = re.findall(r"```sql\s*(.*?)\s*```", content + "\n" + design_doc, re.DOTALL | re.IGNORECASE)
            ddl_blocks = [b.strip() for b in sql_blocks if "CREATE TABLE" in b.upper()]
            if not ddl_blocks:
                from agents.src.shared.llm import llm_invoke_with_retry
                ddl_resp = llm_invoke_with_retry(
                    _llm,
                    f"Write a complete SQL DDL script (CREATE TABLE statements with primary keys, foreign keys, and indexes) for this system design, using the SQL dialect of the database it specifies (PostgreSQL if unspecified). Respond ONLY with raw SQL inside a ```sql block:\n\n{design_doc[:3500]}"
                )
                sql_blocks = re.findall(r"```(?:sql)?\s*(.*?)\s*```", ddl_resp.content, re.DOTALL | re.IGNORECASE)
                ddl_blocks = [b.strip() for b in sql_blocks if "CREATE TABLE" in b.upper()]
                if not ddl_blocks and "CREATE TABLE" in ddl_resp.content.upper():
                    ddl_blocks = [ddl_resp.content.strip()]
            if ddl_blocks:
                init_sql_path.parent.mkdir(parents=True, exist_ok=True)
                init_sql_path.write_text("\n\n".join(ddl_blocks) + "\n", encoding="utf-8")
                print(f"DB Engineer extracted {len(ddl_blocks)} SQL DDL block(s) into db/init.sql")

    except Exception as e:
        print(f"DB Engineer JSON parsing failed: {e}")
    
    return {"iteration_count": state.iteration_count + 1}


# ---------------------------------------------------------------------------
# 3. Execute Migrations Node
# ---------------------------------------------------------------------------
def execute_migrations_node(state: DatabaseEngineerState) -> dict:
    """
    Runs the migrations against the newly created database.
    """
    if "Skipped:" in (state.migration_logs or ""):
        print("DB Engineer: Skipping execution (no DB required).")
        return {"migration_logs": state.migration_logs}
        
    try:
        logs = run_migrations.invoke({"connection_string": state.db_connection_string, "tech_stack_hint": "sql"})
    except Exception as e:
        logs = str(e)
        
    return {"migration_logs": logs}


# ---------------------------------------------------------------------------
# 4. Validate Schema Node
# ---------------------------------------------------------------------------
def validate_schema_node(state: DatabaseEngineerState) -> dict:
    """
    Compares the physical database schema against the design document.
    """
    if "Skipped:" in (state.migration_logs or ""):
        print("DB Engineer: Skipping schema validation (no DB required).")
        return {"db_schema_ready": True, "schema_diff_notes": "SCHEMA_MATCH (No DB required)"}

    try:
        diff_notes = validate_schema_diff.invoke({
            "connection_string": state.db_connection_string, 
            "design_markdown": state.final_design_doc
        })
    except Exception as e:
        diff_notes = str(e)
        
    is_ready = diff_notes.strip().startswith("SCHEMA_MATCH")
    try:
        from agents.src.shared.tools import get_output_dir
        docs_dir = get_output_dir() / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        report_md = (
            f"# Database Engineering & Migration Report\n\n"
            f"- **Connection String:** `{state.db_connection_string}`\n"
            f"- **Schema Ready:** `{is_ready}`\n\n"
            f"## Migration Execution Logs\n```\n{state.migration_logs or 'N/A'}\n```\n\n"
            f"## Schema Diff Validation\n```\n{diff_notes}\n```\n"
        )
        (docs_dir / "06_database_migration_report.md").write_text(report_md, encoding="utf-8")
    except Exception:
        pass
    return {"db_schema_ready": is_ready, "schema_diff_notes": diff_notes}

# ---------------------------------------------------------------------------
# Task Queue Management
# ---------------------------------------------------------------------------
def pop_task_node(state: DatabaseEngineerState) -> dict:
    tasks = list(state.workflow_tasks)
    if not tasks:
        return {"current_task": None}
    next_task = tasks.pop(0)
    return {"workflow_tasks": tasks, "current_task": next_task}

def mark_task_complete_node(state: DatabaseEngineerState) -> dict:
    return {"current_task": None}

def push_to_github_node(state: DatabaseEngineerState) -> dict:
    """Pushes the current output directory to GitHub with a descriptive commit."""
    from agents.src.shared.github import push_to_github
    current_task = state.current_task or {}
    context = {
        "project_name":      getattr(state, "project_name", "") or "",
        "task_title":        current_task.get("title", "") if isinstance(current_task, dict) else "",
        "task_description":  current_task.get("description", "") if isinstance(current_task, dict) else "",
        "completed_tasks":   list(getattr(state, "completed_task_titles", []) or []),
        "files_changed":     [],  # DB engineer writes migrations; no explicit file list in state
        "scope":             "db",
        "linter_clean":      None,  # No linter concept for DB migrations
    }
    res = push_to_github(state.github_repo_name, "Database Engineer", context=context)
    return {"active_pr_number": res.get("pr_number", 0)}
