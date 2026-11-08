from enum import Enum

class AgentType(str, Enum):
    PLANNING = "planning"
    PRODUCT_MANAGER = "product_manager"
    ARCHITECT = "architect"
    TASK_BREAKDOWN = "task_breakdown"
    BACKEND_DEV = "backend_dev"
    FRONTEND_DEV = "frontend_dev"
    DATABASE_ENGINEER = "database_engineer"
    QA = "qa"
    REVIEWER = "reviewer"
    DEVOPS = "devops"
    SECURITY = "security"
    