"""
Shared Pydantic Schemas for Qbit Multi-Agent System

This module provides type-safe contracts between:
- Central Hub (orchestrator)
- Fullstack Agent (code generator)
- Routes (API layer)

All structured output uses these schemas for validation.
"""

from schemas.scp import (
    FeatureSchema,
    TechStackSchema,
    ExistingContextSchema,
    SCPSchema,
    CentralHubOutput,
)

from schemas.agent import (
    FileSchema,
    AgentOutputSchema,
)

__all__ = [
    # SCP and Hub schemas
    "FeatureSchema",
    "TechStackSchema",
    "ExistingContextSchema",
    "SCPSchema",
    "CentralHubOutput",
    # Agent schemas
    "FileSchema",
    "AgentOutputSchema",
]
