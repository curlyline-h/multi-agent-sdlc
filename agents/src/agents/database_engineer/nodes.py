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
from agents.src.shared.llm import get_llm, llm_tool_invoke_with_retry, execute_tool_calls
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

def _is_db_required(design_doc: str) -> bool:
    if len(design_doc.strip()) < 50:
        return True # Default to true if missing
    design_lower = design_doc.lower()
    no_db_signals = [
        "no database", "no db", "database: none", "in-memory", "localstorage",
        "browser game", "client-side only", "client side only", "static site",
        "no backend", "no server", "no persistent", "file-based", "no persistence"
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


from agents.src.shared.schemas import GeneratedFile, CodeGenerationResponse

from agents.src.shared.context import build_codebase_context

def _get_codebase_summary() -> str:
    return build_codebase_context(
        subdir="db",
        allowed_extensions={".sql", ".prisma", ".json", ".md"},
        empty_message="No generated database scripts found yet.",
    )

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
        from agents.src.shared.workspace import get_output_dir as _get_out
        readme_path = _get_out() / "db" / "README.md"
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
        design_doc=(state.final_design_doc or "")[:2200],
        existing_code=existing_code[:1200],
        logs=(state.migration_logs or "None.")[:500],
        diff=(state.schema_diff_notes or "None.")[:500]
    )
    
    formatted += "\n\nCRITICAL: You MUST output ONLY valid JSON matching this schema:\n{\n  \"files\": [\n    {\"path\": \"output/db/init.sql\", \"content\": \"raw code\"}\n  ]\n}\n\nNote: You have FULL terminal and file system access. You can call `run_terminal_command`, `semantic_code_search`, `read_file_range`, `replace_file_content`, `list_directory`, `fetch_server_logs`, `search_web`, and `rag_search` to inspect the workspace or look up documentation. Gather whatever context you need first. Once ready, output your final payload wrapped EXACTLY in a ```json block matching the CodeGenerationResponse schema. DO NOT output anything else after the JSON block."
    
    import os
    if os.name == 'nt':
        formatted += "\n\nOS RULE: The terminal is Windows cmd.exe. DO NOT use Linux commands like `mkdir -p`, `rm -rf`, or `touch`. Use Windows equivalents (e.g., `mkdir` without `-p` to create directories, `del /s /q` or `rmdir /s /q` for deletion). `mkdir` automatically creates intermediate directories in cmd."
        
    tools_list = [run_terminal_command, semantic_code_search, read_file_range, replace_file_content, list_directory, fetch_server_logs, search_web, rag_search, create_project_database, run_migrations, validate_schema_diff]
    llm_with_tools = _llm.bind_tools(tools_list)
    
    messages: list[Any] = [
        SystemMessage(content="You are a Principal Database Engineer. You write sql migrations."),
        HumanMessage(content=formatted)
    ]
    
    # ReAct Loop
    turn_limit = 15
    for turn in range(turn_limit):
        try:
            response = llm_tool_invoke_with_retry(llm_with_tools, messages, agent_name="Database Engineer", tools=tools_list)
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
        if isinstance(response.content, str) and "```json" in response.content:
            break
            
        tool_map = {tool.name: tool for tool in tools_list}
        messages.extend(execute_tool_calls(response.tool_calls, tool_map, agent_name="Database Engineer"))

    try:
        # Find the content containing the JSON
        content = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and isinstance(msg.content, str) and "```json" in msg.content:
                content = msg.content
                break
        if not content:
            raw_content = messages[-1].content if hasattr(messages[-1], "content") else str(messages[-1])
            content = raw_content if isinstance(raw_content, str) else json.dumps(raw_content)
            
        json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
        if not json_match:
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            
        if json_match:
            parsed = json.loads(json_match.group(1) if '```' in content else json_match.group(0))
        else:
            parsed = json.loads(content)
            
        parsed_response = CodeGenerationResponse(**parsed)
        
        from agents.src.shared.workspace import get_output_dir
        output_dir = get_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for f in parsed_response.files:
            clean_path = f.path.lstrip("/")
            if clean_path.startswith("output/"): clean_path = clean_path[7:]
            file_path = output_dir / clean_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content, encoding="utf-8")
            print(f"DB Engineer wrote: {f.path}")
            
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
    res = push_to_github(state.github_repo_name or "", "Database Engineer", context=context)
    return {"active_pr_number": res.get("pr_number", 0)}
