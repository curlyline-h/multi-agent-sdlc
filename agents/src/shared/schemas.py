from typing import List
from pydantic import BaseModel, Field


class GeneratedFile(BaseModel):
    path: str = Field(description="The relative path to save the file to, e.g. src/app/page.tsx")
    content: str = Field(description="The full raw code content of the file")


class CodeGenerationResponse(BaseModel):
    terminal_commands: List[str] = Field(
        default_factory=list,
        description="List of shell commands to execute to set up the environment, e.g. ['npm install zod']",
    )
    files: List[GeneratedFile] = Field(description="List of files to generate or update")
