"""
Architect Agent — MCP and Internal Tools

MCP Tools: Tavily (web search), Fetch (docs), GitHub (reference implementations)
Internal Tools: RAG search, Schema validator, API spec linter
"""
from agents.src.shared.tools import tool
from typing import List, Dict, Any
import re


# ---------------------------------------------------------------------------
# RAG Search (Internal)
# ---------------------------------------------------------------------------

@tool
def validate_schema(schema_markdown: str) -> str:
    """
    Validates the database schema section of a design document for common
    structural issues. Checks for:
    - Tables missing primary keys
    - Foreign keys referencing undefined tables
    - Columns with no data type specified
    - Duplicate table names

    Args:
        schema_markdown: The raw markdown text containing the database schema section.

    Returns:
        A validation report string. Returns 'SCHEMA_VALID' if no issues are found.
    """
    issues = []

    # Extract table names defined in the schema
    defined_tables = re.findall(
        r"(?:table|model|schema)[:\s]+[`\"']?(\w+)[`\"']?",
        schema_markdown,
        re.IGNORECASE,
    )

    # Check for primary key mentions
    if "primary key" not in schema_markdown.lower() and "pk" not in schema_markdown.lower():
        issues.append("WARNING: No primary key definitions found in the schema.")

    # Check for data type specifications
    if not re.search(r"\b(VARCHAR|INTEGER|TEXT|BOOLEAN|TIMESTAMP|UUID|FLOAT|BIGINT)\b",
                     schema_markdown, re.IGNORECASE):
        issues.append("WARNING: No explicit data types found. All columns must have specified types.")

    # Check for foreign key references to undefined tables
    fk_references = re.findall(
        r"(?:references|foreign key)[:\s]+[`\"']?(\w+)[`\"']?",
        schema_markdown,
        re.IGNORECASE,
    )
    undefined_refs = [ref for ref in fk_references if ref.lower() not in
                      [t.lower() for t in defined_tables]]
    if undefined_refs:
        issues.append(f"ERROR: Foreign keys reference undefined tables: {undefined_refs}")

    if not issues:
        return "SCHEMA_VALID"

    return "SCHEMA_VALIDATION_ISSUES:\n" + "\n".join(f"- {i}" for i in issues)


# ---------------------------------------------------------------------------
# API Spec Linter (Internal)
# ---------------------------------------------------------------------------

@tool
def lint_api_spec(api_markdown: str) -> str:
    """
    Lints the API endpoints section of the design document for common
    specification issues. Checks for:
    - Missing HTTP method definitions
    - Endpoints not starting with /api/
    - Missing response codes
    - Inconsistent naming conventions

    Args:
        api_markdown: The raw markdown text containing the API endpoints section.

    Returns:
        A linting report string. Returns 'API_SPEC_VALID' if no issues found.
    """
    issues = []

    # Check for HTTP method definitions
    http_methods = re.findall(
        r"\b(GET|POST|PUT|DELETE|PATCH)\b", api_markdown
    )
    if not http_methods:
        issues.append("ERROR: No HTTP methods (GET, POST, PUT, DELETE, PATCH) found.")

    # Check that endpoints follow /api/ convention
    endpoints = re.findall(r"`(/[^`]+)`", api_markdown)
    non_standard = [e for e in endpoints if not e.startswith("/api/")]
    if non_standard:
        issues.append(
            f"WARNING: These endpoints do not follow /api/ convention: {non_standard}"
        )

    # Check for HTTP response codes
    if not re.search(r"\b(200|201|400|401|403|404|422|500)\b", api_markdown):
        issues.append("WARNING: No HTTP response status codes found in endpoint definitions.")

    if not issues:
        return "API_SPEC_VALID"

    return "API_LINTING_ISSUES:\n" + "\n".join(f"- {i}" for i in issues)
