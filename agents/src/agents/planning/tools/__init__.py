"""
Internal tools available to the Planning Agent.
These are simple Python callables exposed as LangChain tools.
"""
import json
from typing import List
from agents.src.shared.tools import tool

# ---------------------------------------------------------------------------
# RAG Search Tool
# ---------------------------------------------------------------------------
# Lazily import to avoid circular imports at module load time
@tool
def parse_structured_output(raw_output: str) -> dict:
    """
    Extracts the structured JSON block from the planning agent's raw markdown output.
    Returns a dict with keys: complexity_level, project_type,
    recommended_tech_stack, risks, constraints.
    """
    try:
        start = raw_output.rfind("```json")
        end = raw_output.rfind("```", start + 1)
        if start == -1 or end == -1:
            return {"error": "No JSON block found in output."}
        json_str = raw_output[start + 7:end].strip()
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        return {"error": f"JSON parse failed: {str(e)}"}
