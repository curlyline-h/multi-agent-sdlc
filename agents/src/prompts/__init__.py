import os
from langchain_core.prompts import PromptTemplate

def _load_prompt(filename: str) -> PromptTemplate:
    """
    Helper function to load raw text templates from disk and wrap them in LangChain PromptTemplates.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, filename)
    with open(file_path, "r", encoding="utf-8") as f:
        template_text = f.read()
    
    # Automatically extracts formatting variables (e.g. {user_req})
    return PromptTemplate.from_template(template_text)

# Expose LangChain PromptTemplates for all agents
planning_prompt = _load_prompt("planning.txt")
product_manager_prompt = _load_prompt("product_manager.txt")
architect_prompt = _load_prompt("architect.txt")
task_breakdown_prompt = _load_prompt("task_breakdown.txt")
database_engineer_prompt = _load_prompt("database_engineer.txt")
backend_dev_prompt = _load_prompt("backend_dev.txt")
frontend_dev_prompt = _load_prompt("frontend_dev.txt")
qa_prompt = _load_prompt("qa.txt")
reviewer_prompt = _load_prompt("reviewer.txt")
devops_prompt = _load_prompt("devops.txt")
security_prompt = _load_prompt("security.txt")
