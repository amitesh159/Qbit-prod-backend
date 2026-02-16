"""
Fullstack Agent Output Schemas

These schemas define the structure of code generation output.
CRITICAL: All schemas are designed for Cerebras structured output compatibility.
NO Dict[str, Any] or Dict[str, str] allowed - they create additionalProperties which Cerebras rejects.
"""

from pydantic import BaseModel, Field
from typing import List, Optional


# ============================================================================
# KEY-VALUE MODELS (for Dict replacement)
# ============================================================================

class KeyValuePair(BaseModel):
    """Key-value pair for dependencies and environment variables"""
    key: str = Field(description="Package name or variable name")
    value: str = Field(description="Version or value")


# ============================================================================
# FILE SCHEMA
# ============================================================================

class FileSchema(BaseModel):
    """Single file output schema"""
    path: str = Field(
        description="File path starting with /frontend/ or /backend/"
    )
    content: str = Field(
        description="Complete file content - NO placeholders like '... keep existing code'"
    )
    action: str = Field(
        default="create",
        description="Action to perform: create | modify | delete"
    )


# ============================================================================
# DEPENDENCIES SCHEMA
# ============================================================================

class DependenciesSchema(BaseModel):
    """Dependencies structure for frontend and backend"""
    frontend: List[KeyValuePair] = Field(
        default=[],
        description="Frontend dependencies as list of {key: package, value: version}"
    )
    backend: List[KeyValuePair] = Field(
        default=[],
        description="Backend dependencies as list of {key: package, value: version}"
    )


# ============================================================================
# AGENT OUTPUT SCHEMA
# ============================================================================

class AgentOutputSchema(BaseModel):
    """Fullstack Agent complete output schema - Cerebras compatible"""
    files: List[FileSchema] = Field(
        description="List of files to generate/modify",
        default=[]
    )
    dependencies: DependenciesSchema = Field(
        default_factory=DependenciesSchema,
        description="Dependencies by tier with explicit key-value pairs"
    )
    environment_variables: List[KeyValuePair] = Field(
        default=[],
        description="Environment variables as list of {key: var_name, value: var_value}"
    )
    instructions: Optional[str] = Field(
        None,
        description="Setup instructions for user"
    )
    tool_usage_summary: Optional[str] = Field(
        None,
        description="Summary of which tools were used and why"
    )
    error: Optional[str] = Field(
        None,
        description="Error message if generation failed"
    )
