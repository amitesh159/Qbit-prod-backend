"""
Pydantic Models for MongoDB Collections
All database schemas with validation - V2 Schema
"""
from typing import List, Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field


# ============================================================================
# USER SCHEMAS
# ============================================================================
class UserModel(BaseModel):
    """User account schema"""
    user_id: str = Field(..., description="Unique user identifier (UUID)")
    email: str = Field(..., description="User email address")
    display_name: str | None = Field(None, description="User display name")
    password_hash: str | None = Field(None, description="Hashed password (if email auth)")
    
    # OAuth
    github_username: str | None = Field(None, description="GitHub username")
    github_id: str | None = Field(None, description="GitHub user ID")
    github_access_token: str | None = Field(None, description="GitHub OAuth access token")
    
    # Credits
    credits: int = Field(default=100, description="Available credits")
    tier: Literal["free", "paid"] = Field(default="free", description="User tier")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login: datetime | None = None
    
    # Community stats
    public_project_count: int = Field(default=0, description="Count of public projects")
    total_forks_received: int = Field(default=0, description="Total forks across all projects")


# ============================================================================
# PROJECT SCHEMAS
# ============================================================================
class ProjectSummary(BaseModel):
    """Project summary for Knowledge Base"""
    architecture: str = Field(..., description="High-level architecture description")
    stack: List[str] = Field(default_factory=list, description="Tech stack list")
    entry_points: List[str] = Field(default_factory=list, description="Main entry files")
    major_modules: List[str] = Field(default_factory=list, description="Major module names")
    constraints: List[str] = Field(default_factory=list, description="Project constraints")
    token_estimate: int = Field(default=0, description="Estimated tokens for summary")


class ProjectModel(BaseModel):
    """Project schema"""
    project_id: str = Field(..., description="Unique project identifier (UUID)")
    user_id: str = Field(..., description="Owner user ID")
    name: str = Field(..., description="Project name")
    description: str | None = Field(None, description="Project description")
    
    # Current state
    current_snapshot_id: str | None = Field(None, description="Current snapshot ID")
    
    # Knowledge Base summary
    summary: ProjectSummary | None = None
    
    # Community/Public features
    is_public: bool = Field(default=False, description="Whether project is public")
    is_featured: bool = Field(default=False, description="Admin-featured flag")
    screenshot_url: str | None = Field(None, description="Screenshot URL for preview card")
    preview_url: str | None = Field(None, description="Last known E2B preview URL")
    tags: List[str] = Field(default_factory=list, description="Project tags for filtering")
    view_count: int = Field(default=0, description="Number of times viewed")
    fork_count: int = Field(default=0, description="Number of times forked")
    forked_from: str | None = Field(None, description="Parent project ID if forked")
    
    # State
    is_deleted: bool = Field(default=False, description="Soft delete flag")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SCP (SPECIFICATION) SCHEMAS
# ============================================================================
class SCPModel(BaseModel):
    """SCP (Structured Context Protocol) document schema"""
    scp_id: str = Field(..., description="Unique SCP identifier (UUID)")
    project_id: str = Field(..., description="Project this SCP belongs to")
    version: str = Field(..., description="SCP version (e.g., 1.0, 1.1)")
    
    # The actual SCP document
    document: Dict[str, Any] = Field(..., description="Full SCP JSON document")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SCPVersionModel(BaseModel):
    """SCP Version schema (for scp_versions collection)"""
    project_id: str = Field(..., description="Project this SCP belongs to")
    version: str = Field(..., description="SCP version (e.g., 1.0, 1.1)")
    scp_document: Dict[str, Any] = Field(..., description="Full SCP JSON document")
    created_at: datetime = Field(default_factory=datetime.utcnow)



# ============================================================================
# MODULE SCHEMAS
# ============================================================================
class ModuleModel(BaseModel):
    """Module/folder schema"""
    module_id: str = Field(..., description="Unique module identifier (UUID)")
    project_id: str
    path: str = Field(..., description="Module path (e.g., /frontend/components)")
    name: str = Field(..., description="Module name")
    description: str = Field(..., description="Module responsibility description")
    public_exports: List[str] = Field(default_factory=list, description="Exported entities")
    key_files: List[str] = Field(default_factory=list, description="Important files in module")
    token_estimate: int = Field(default=150, description="Estimated tokens")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CODE FILE SCHEMAS
# ============================================================================
class CodeFileModel(BaseModel):
    """Source code file storage schema"""
    file_id: str = Field(..., description="Unique file identifier (UUID)")
    project_id: str = Field(..., description="Project this file belongs to")
    
    # File identity
    path: str = Field(..., description="File path (e.g., /frontend/app/page.tsx)")
    content: str = Field(..., description="Actual source code")
    content_hash: str = Field(..., description="SHA-256 hash for deduplication")
    
    # Metadata
    language: str = Field(..., description="Programming language")
    size_bytes: int = Field(default=0, description="File size in bytes")
    line_count: int = Field(default=0, description="Number of lines")
    
    # State
    is_compressed: bool = Field(default=False, description="Whether content is compressed")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# FILE METADATA SCHEMAS
# ============================================================================
class FileAnchors(BaseModel):
    """Code anchors for precise targeting"""
    imports: List[str] = Field(default_factory=list, description="Import statements")
    exports: List[str] = Field(default_factory=list, description="Export statements")
    functions: List[str] = Field(default_factory=list, description="Function names")
    components: List[str] = Field(default_factory=list, description="Component names")
    classes: List[str] = Field(default_factory=list, description="Class names")


class FileMetadataModel(BaseModel):
    """File metadata schema (separate from content)"""
    metadata_id: str = Field(..., description="Unique metadata identifier (UUID)")
    project_id: str
    
    # File identity
    path: str = Field(..., description="File path")
    language: str = Field(..., description="Programming language")
    
    # Metrics
    line_count: int = Field(default=0)
    token_estimate: int = Field(default=0)
    
    # Version tracking
    current_hash: str = Field(..., description="Current content hash")
    
    # Code structure
    summary: str = Field(default="", description="File responsibility summary")
    anchors: FileAnchors = Field(default_factory=FileAnchors)
    dependencies: List[str] = Field(default_factory=list, description="File dependencies")
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SNAPSHOT SCHEMAS
# ============================================================================
class SnapshotModel(BaseModel):
    """Project snapshot for version control"""
    snapshot_id: str = Field(..., description="Unique snapshot ID (UUID)")
    project_id: str
    
    # Version info
    label: str | None = Field(None, description="Optional user label")
    scp_version: str = Field(..., description="SCP version at snapshot")
    
    # File references (FIXED: array of file_ids, not hash dict)
    file_ids: List[str] = Field(default_factory=list, description="List of file IDs in this snapshot")
    
    # LangGraph store integration
    stored_in_langgraph: bool = Field(default=False, description="Whether snapshot is persisted in LangGraph store")
    store_namespace: str | None = Field(None, description="LangGraph store namespace")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# OPERATION SCHEMAS
# ============================================================================
class OperationModel(BaseModel):
    """Operation log for audit trail"""
    operation_id: str = Field(..., description="Unique operation ID (UUID)")
    project_id: str
    
    # What happened
    type: Literal["create", "modify", "delete", "rollback"] = Field(..., description="Operation type")
    affected_paths: List[str] = Field(default_factory=list, description="Affected file paths")
    description: str = Field(..., description="Human-readable change summary")
    
    # Context
    user_prompt: str = Field(..., description="User's original request")
    agent: str = Field(..., description="Agent that executed")
    snapshot_id: str = Field(..., description="Snapshot created after operation")
    
    # Patches (for modify operations)
    patches: List[Dict[str, Any]] | None = Field(None, description="JSON patches")
    
    # Result
    success: bool = Field(default=True)
    error_message: str | None = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# CONVERSATION SCHEMAS
# ============================================================================
class ConversationTurn(BaseModel):
    """Single conversation turn"""
    role: Literal["user", "assistant"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationModel(BaseModel):
    """Conversation history"""
    conversation_id: str = Field(..., description="Unique conversation ID (UUID)")
    project_id: str
    session_id: str = Field(..., description="Session identifier")
    turns: List[ConversationTurn] = Field(default_factory=list)
    summary: str = Field(default="", description="Conversation summary")
    token_estimate: int = Field(default=200)
    
    # LangGraph thread management
    thread_id: str | None = Field(None, description="LangGraph thread ID for persistent memory")
    checkpoint_namespace: str | None = Field(None, description="LangGraph checkpoint namespace")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ConversationMessageModel(BaseModel):
    """Individual conversation message for memory caching"""
    message_id: str = Field(..., description="Unique message ID (UUID)")
    project_id: str = Field(..., description="Project this message belongs to")
    role: Literal["user", "assistant"] = Field(..., description="Message role")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)



# ============================================================================
# CREDIT HISTORY SCHEMAS
# ============================================================================
class CreditHistoryModel(BaseModel):
    """Credit transaction log"""
    transaction_id: str = Field(..., description="Unique transaction ID (UUID)")
    user_id: str = Field(..., description="User ID")
    
    amount: int = Field(..., description="Credit change (positive = credit, negative = debit)")
    operation: str = Field(..., description="Operation description")
    project_id: str | None = None
    
    balance_after: int = Field(..., description="Balance after this transaction")
    
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ============================================================================
# SANDBOX SESSION SCHEMAS
# ============================================================================
class SandboxSessionModel(BaseModel):
    """E2B sandbox session tracking"""
    session_id: str = Field(..., description="Unique session ID (UUID)")
    project_id: str = Field(..., description="Project this sandbox belongs to")
    
    # E2B sandbox info
    sandbox_id: str | None = Field(None, description="E2B sandbox ID")
    preview_url: str | None = Field(None, description="Current preview URL")
    
    status: Literal["active", "expired", "error"] = Field(
        default="expired", 
        description="Sandbox status"
    )
    
    # Server config
    server_command: str = Field(default="npm run dev", description="Command to start server")
    port: int = Field(default=3000, description="Server port")
    
    # Timestamps
    last_active: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = Field(None, description="Expiration time")


# ============================================================================
# USER SETTINGS SCHEMAS
# ============================================================================
class UserSettingsModel(BaseModel):
    """User preferences and settings"""
    user_id: str = Field(..., description="User ID (1:1 with users)")
    
    # Coding preferences
    coding_style: str = Field(default="functional components, hooks over classes")
    naming_conventions: str = Field(default="camelCase for variables, PascalCase for components")
    testing_policy: str = Field(default="unit tests for utils, integration tests for APIs")
    
    # UI preferences
    theme: Literal["light", "dark", "system"] = Field(default="system")
    default_tech_stack: List[str] = Field(
        default_factory=lambda: ["React", "TypeScript", "TailwindCSS"]
    )
    
    updated_at: datetime = Field(default_factory=datetime.utcnow)
