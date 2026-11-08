from pydantic import BaseModel,Field
import datetime


class AgentLog(BaseModel):
    timestamp: datetime = Field(description="Timestamp of the log")
    agent_id: str = Field(description="ID of the agent")
    agent_name:str = Field(description="Name of the agent")
    message: str = Field(description="Message from the agent")
    level: str= Field(description="Level of the log")
    