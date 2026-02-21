"""
Fullstack Agent Output Schemas

These schemas define the structure of code generation output.
CRITICAL: All schemas are designed for Cerebras structured output compatibility.
NO Dict[str, Any] or Dict[str, str] allowed - they create additionalProperties which Cerebras rejects.

QAP (Qbit Agentic Protocol):
- FileOperation: write (create/overwrite) | modify (targeted patch) | delete
- Agent decides operations; generation_routes.py executor applies them.
- This makes follow-ups targeted, not full regenerations.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal


# ============================================================================
# KEY-VALUE MODELS (for Dict replacement)
# ============================================================================

class KeyValuePair(BaseModel):
    """Key-value pair for dependencies and environment variables"""
    key: str = Field(description="Package name or variable name")
    value: str = Field(description="Version or value")


# ============================================================================
# QAP FILE OPERATION SCHEMA
# ============================================================================

class FileOperation(BaseModel):
    """
    Qbit Agentic Protocol (QAP) file operation.

    The LLM decides the operation; the executor applies it:
    - write:  Create or completely overwrite a file. Use for new files and new projects.
    - modify: Replace a specific block of text inside an existing file.
              Use for follow-ups to minimize diff: only touch what changed.
    - delete: Remove a file entirely.
    """
    operation: Literal["write", "modify", "delete"] = Field(
        description="Operation type: write (create/overwrite), modify (targeted patch), delete"
    )
    path: str = Field(
        description="File path starting with /frontend/ or /backend/"
    )
    content: Optional[str] = Field(
        default=None,
        description="Complete file content for 'write' operation. Must be the full file."
    )
    search: Optional[str] = Field(
        default=None,
        description="Exact string to find in the existing file for 'modify' operation. Must match exactly including whitespace."
    )
    replace: Optional[str] = Field(
        default=None,
        description="Replacement string for the 'modify' operation. Replaces the first occurrence of 'search'."
    )
    reason: Optional[str] = Field(
        default=None,
        description="Brief explanation of why this operation is needed. Helps with debugging."
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
# AGENT OUTPUT SCHEMA (QAP-based)
# ============================================================================

class AgentOutputSchema(BaseModel):
    """
    Fullstack Agent complete output schema - Cerebras compatible.

    Uses QAP operations instead of raw file dumps:
    - Agent decides write / modify / delete for each file
    - generation_routes.py executor processes operations in order
    - manifest fields (files_written, files_modified, new_packages) for orchestrator
    """
    # Reasoning (for debugging and transparency via WebSocket)
    reasoning: Optional[str] = Field(
        default=None,
        description="Agent reasoning: what it built, why it chose each operation, what the primary visual impression will be."
    )

    # QAP Operations (executed by generation_routes.py)
    file_operations: List[FileOperation] = Field(
        default=[],
        description="Ordered list of file operations: write, modify, or delete. This is what the executor processes."
    )

    # Legacy compatibility: kept for DB saving and KB indexing
    # Populated by generation_routes.py after processing operations
    dependencies: DependenciesSchema = Field(
        default_factory=DependenciesSchema,
        description="Dependencies by tier with explicit key-value pairs"
    )
    environment_variables: List[KeyValuePair] = Field(
        default=[],
        description="Environment variables as list of {key: var_name, value: var_value}"
    )

    # Manifest (populated by agent for orchestrator use)
    files_written: List[str] = Field(
        default=[],
        description="Paths of files created/overwritten in this call (write operations)"
    )
    files_modified: List[str] = Field(
        default=[],
        description="Paths of files patched in this call (modify operations)"
    )
    files_deleted: List[str] = Field(
        default=[],
        description="Paths of files deleted in this call (delete operations)"
    )
    new_packages: List[str] = Field(
        default=[],
        description="NPM packages needed that are NOT pre-installed in the E2B template. e.g. ['react-confetti@6.1.0']"
    )

    # Server info
    primary_route: str = Field(
        default="/",
        description="The main route to show in the preview after generation, e.g. '/dashboard'"
    )

    # Instructions and error (preserved from legacy)
    instructions: Optional[str] = Field(
        default=None,
        description="Setup instructions for user"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if generation failed"
    )
