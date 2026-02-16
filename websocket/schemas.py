"""
WebSocket Message Schemas
Pydantic models for type-safe WebSocket message validation
"""
from typing import Literal, List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ============================================================================
# BASE MESSAGE SCHEMA
# ============================================================================
class WSMessageBase(BaseModel):
    """Base WebSocket message structure"""
    type: str = Field(..., description="Message type identifier")
    payload: Dict[str, Any] = Field(..., description="Message payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Message timestamp (ISO format)"
    )


# ============================================================================
# PAYLOAD SCHEMAS
# ============================================================================
class PromptReceivedPayload(BaseModel):
    """User prompt captured"""
    prompt: str = Field(..., description="User's input prompt")
    discussion_mode: bool = Field(default=False, description="Whether in discussion mode")


class SCPGeneratedPayload(BaseModel):
    """SCP generation complete"""
    scp: Dict[str, Any] = Field(..., description="Full SCP document")
    summary: str = Field(..., description="Human-readable SCP summary")
    complexity: Literal["simple", "moderate", "complex"] = Field(..., description="Project complexity")
    credits_required: int = Field(..., description="Credits needed for generation")
    file_count: int = Field(default=0, description="Number of files to generate")


class AgentTask(BaseModel):
    """Individual agent task"""
    id: str = Field(..., description="Unique task ID")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Task description")
    status: Literal["pending", "in-progress", "done", "error", "need-help"] = Field(
        ..., 
        description="Current task status"
    )
    priority: Literal["high", "medium", "low"] = Field(default="medium", description="Task priority")
    progress: Optional[int] = Field(None, description="Progress percentage (0-100)")
    tools: List[str] = Field(default_factory=list, description="MCP server tools used")


class AgentTaskUpdatePayload(BaseModel):
    """Agent task progress update"""
    tasks: List[AgentTask] = Field(..., description="List of agent tasks with current status")
    current_task_id: Optional[str] = Field(None, description="ID of currently executing task")


class CodeTokenPayload(BaseModel):
    """Code streaming token"""
    file_path: str = Field(..., description="File being generated")
    token: str = Field(..., description="Code token (chunk)")
    is_complete: bool = Field(default=False, description="True if this is the last token for the file")
    language: str = Field(default="typescript", description="Programming language")
    line_number: Optional[int] = Field(None, description="Current line number")


class SandboxStatusPayload(BaseModel):
    """E2B sandbox deployment status"""
    stage: Literal["creating", "deploying", "installing", "starting", "ready", "error"] = Field(
        ..., 
        description="Current deployment stage"
    )
    message: str = Field(..., description="Human-readable status message")
    sandbox_id: Optional[str] = Field(None, description="E2B sandbox ID")
    logs: List[str] = Field(default_factory=list, description="Recent sandbox logs")
    progress: Optional[int] = Field(None, description="Progress percentage (0-100)")


class ConversationTurnPayload(BaseModel):
    """Conversation history entry"""
    role: Literal["user", "assistant", "system"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class CodeGenerationProgressPayload(BaseModel):
    """Generic code generation progress (legacy compatibility)"""
    stage: str = Field(..., description="Current stage name")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    message: str = Field(..., description="Status message")


class CodeGenerationCompletePayload(BaseModel):
    """Code generation completion"""
    project_id: str = Field(..., description="Generated project ID")
    preview_url: str = Field(..., description="Sandbox preview URL")
    scp_version: str = Field(..., description="SCP version used")
    credits_used: int = Field(..., description="Credits deducted")
    file_count: int = Field(default=0, description="Number of files generated")


class ErrorPayload(BaseModel):
    """Error notification"""
    message: str = Field(..., description="Error description")
    code: str = Field(..., description="Error code identifier")
    retry_allowed: bool = Field(default=False, description="Whether retry is possible")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")


# ============================================================================
# MESSAGE BUILDERS
# ============================================================================
class WSMessageFactory:
    """Factory for creating type-safe WebSocket messages"""
    
    @staticmethod
    def prompt_received(prompt: str, discussion_mode: bool = False) -> Dict[str, Any]:
        """Create prompt_received message"""
        return {
            "type": "prompt_received",
            "payload": PromptReceivedPayload(
                prompt=prompt,
                discussion_mode=discussion_mode
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def scp_generated(
        scp: Dict[str, Any],
        summary: str,
        complexity: str,
        credits_required: int,
        file_count: int = 0
    ) -> Dict[str, Any]:
        """Create scp_generated message"""
        return {
            "type": "scp_generated",
            "payload": SCPGeneratedPayload(
                scp=scp,
                summary=summary,
                complexity=complexity,
                credits_required=credits_required,
                file_count=file_count
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def agent_task_update(tasks: List[Dict[str, Any]], current_task_id: Optional[str] = None) -> Dict[str, Any]:
        """Create agent_task_update message"""
        task_objects = [AgentTask(**task) for task in tasks]
        return {
            "type": "agent_task_update",
            "payload": AgentTaskUpdatePayload(
                tasks=task_objects,
                current_task_id=current_task_id
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def code_token(file_path: str, token: str, is_complete: bool = False, language: str = "typescript") -> Dict[str, Any]:
        """Create code_token message"""
        return {
            "type": "code_token",
            "payload": CodeTokenPayload(
                file_path=file_path,
                token=token,
                is_complete=is_complete,
                language=language
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def sandbox_status(
        stage: str,
        message: str,
        sandbox_id: Optional[str] = None,
        logs: List[str] = None,
        progress: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create sandbox_status message"""
        return {
            "type": "sandbox_status",
            "payload": SandboxStatusPayload(
                stage=stage,
                message=message,
                sandbox_id=sandbox_id,
                logs=logs or [],
                progress=progress
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def conversation_turn(role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create conversation_turn message"""
        return {
            "type": "conversation_turn",
            "payload": ConversationTurnPayload(
                role=role,
                content=content,
                metadata=metadata
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def code_generation_complete(
        project_id: str,
        preview_url: str,
        scp_version: str,
        credits_used: int,
        file_count: int = 0
    ) -> Dict[str, Any]:
        """Create code_generation_complete message"""
        return {
            "type": "code_generation_complete",
            "payload": CodeGenerationCompletePayload(
                project_id=project_id,
                preview_url=preview_url,
                scp_version=scp_version,
                credits_used=credits_used,
                file_count=file_count
            ).model_dump(),
            "timestamp": datetime.utcnow().isoformat()
        }
