"""
Structured Context Protocol (SCP) and Central Hub Schemas

These schemas define the contract between Central Hub and Fullstack Agent.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any, Optional, Literal


class FeatureSchema(BaseModel):
    """Individual feature specification"""
    name: str = Field(description="Feature name")
    description: str = Field(description="Detailed feature description")
    priority: Optional[Literal["high", "medium", "low"]] = Field(
        default="medium",
        description="Implementation priority"
    )
    implementation_notes: Optional[str] = Field(
        None,
        description="Technical notes for implementation"
    )


class TechStackSchema(BaseModel):
    """Technology stack specification"""
    frontend: List[str] = Field(
        description="Frontend technologies (React, Next.js, Tailwind, etc.)"
    )
    backend: List[str] = Field(
        description="Backend technologies (Node.js, Express, FastAPI, etc.)"
    )
    ai_services: List[str] = Field(
        default_factory=list,
        description="AI/ML services (OpenAI, Anthropic, etc.)"
    )
    
    @staticmethod
    def _coerce_to_list(value):
        """Convert string to list if needed."""
        if isinstance(value, str):
            # Handle "none" or empty
            if value.lower() in ["none", "", "null"]:
                return []
            # Handle comma-separated
            if "," in value:
                return [item.strip() for item in value.split(",") if item.strip()]
            # Single item
            return [value] if value else []
        elif isinstance(value, list):
            return value
        else:
            return []
    
    @field_validator('frontend', 'backend', 'ai_services', mode='before')
    @classmethod
    def coerce_lists(cls, v):
        """Ensure all fields are lists."""
        return cls._coerce_to_list(v)


class ExistingContextSchema(BaseModel):
    """Context for follow-up requests"""
    affected_files: List[str] = Field(
        description="Files that will be modified"
    )
    project_id: str = Field(
        description="Project identifier"
    )
    modification_type: Optional[Literal["feature_addition", "bug_fix", "refactor", "enhancement"]] = Field(
        default="feature_addition",
        description="Type of modification"
    )


class SCPSchema(BaseModel):
    """
    Structured Context Protocol - Complete contract between Hub and Agent
    
    The SCP contains all information needed for the Fullstack Agent to
    generate or modify code without additional clarification.
    """
    version: str = Field(
        default="1.0",
        description="SCP schema version"
    )
    project_overview: str = Field(
        description="High-level architecture and purpose"
    )
    complexity: Literal["simple", "moderate", "complex"] = Field(
        description="Project complexity assessment"
    )
    tech_stack: Dict[str, List[str]] = Field(
        description="Frontend and backend stack (legacy dict format for compatibility)"
    )
    features: List[Dict[str, str]] = Field(
        description="Features with implementation details (legacy dict format)"
    )
    ui_specifications: Dict[str, Any] = Field(
        description="Design tokens, typography, spacing, animations"
    )
    file_structure: Dict[str, List[str]] = Field(
        description="Monorepo structure: {frontend: [...], backend: [...]}"
    )
    constraints: List[str] = Field(
        default_factory=list,
        description="Technical constraints and limitations"
    )
    agent_prompts: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Agent-specific prompts: {fullstack_agent: '...'}"
    )
    existing_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Context for follow-up modifications (affected_files, project_id)"
    )


class CentralHubOutput(BaseModel):
    """
    Complete output from Central Hub (LangChain structured output)
    
    This schema is enforced by Groq/Cerebras JSON schema mode.
    """
    intent: Literal["code_generation", "follow_up", "conversation", "discussion", "ambiguous"] = Field(
        description="Classified user intent"
    )
    complexity: Optional[Literal["simple", "moderate", "complex"]] = Field(
        None,
        description="Project complexity (required for code_generation/follow_up)"
    )
    response: Optional[str] = Field(
        None,
        description="Direct response for conversation/discussion intents"
    )
    scp: Optional[SCPSchema] = Field(
        None,
        description="Structured Context Protocol (required for code_generation/follow_up)"
    )
    agent_invocation: Literal["fullstack_agent", "none"] = Field(
        description="Which agent to invoke (or none for direct response)"
    )
    reasoning: Optional[str] = Field(
        None,
        description="Chain-of-thought reasoning for classification"
    )
