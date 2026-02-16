"""
Project API Routes
Project management endpoints
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from database.connection import get_database
from auth.dependencies import require_auth

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"], redirect_slashes=False)


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================
class ProjectResponse(BaseModel):
    """Project response model"""
    project_id: str
    name: str
    created_at: str
    last_updated: str
    current_snapshot: str | None
    summary: Dict[str, Any] | None
    # Public project fields
    is_public: bool = False
    description: str | None = None
    screenshot_url: str | None = None
    tags: List[str] = []
    view_count: int = 0
    fork_count: int = 0


class SnapshotResponse(BaseModel):
    """Snapshot response model"""
    snapshot_id: str
    timestamp: str
    scp_version: str
    label: str | None


# ============================================================================
# COMMUNITY PROJECT  ROUTES (NO AUTH REQUIRED)
# ============================================================================
@router.get("/community", response_model=List[ProjectResponse])
async def list_community_projects(
    limit: int = 20,
    offset: int = 0,
    tag: str | None = None
):
    """
    Get public/community projects.
    No authentication required - for landing page showcase.
    
    Args:
        limit: Number of projects to return (default 20, max 50)
        offset: Pagination offset
        tag: Optional tag filter
    """
    db = await get_database()
    
    # Build query
    query = {
        "is_public": True,
        "is_deleted": False
    }
    
    if tag:
        query["tags"] = tag
    
    # Fetch projects sorted by view count (popularity)
    projects = await db.projects.find(query).sort(
        "view_count", -1
    ).skip(offset).limit(min(limit, 50)).to_list(length=None)
    
    logger.info(
        "community_projects_listed",
        project_count=len(projects),
        tag_filter=tag
    )
    
    return [
        ProjectResponse(
            project_id=p["project_id"],
            name=p["name"],
            created_at=p["created_at"].isoformat(),
            last_updated=p["last_updated"].isoformat(),
            current_snapshot=p.get("current_snapshot"),
            summary=p.get("summary"),
            is_public=p.get("is_public", False),
            description=p.get("description"),
            screenshot_url=p.get("screenshot_url"),
            tags=p.get("tags", []),
            view_count=p.get("view_count", 0),
            fork_count=p.get("fork_count", 0)
        )
        for p in projects
    ]


@router.get("/community/{project_id}", response_model=ProjectResponse)
async def get_community_project(project_id: str):
    """
    Get single community project details.
    No authentication required.
    Increments view count.
    """
    db = await get_database()
    
    project = await db.projects.find_one({
        "project_id": project_id,
        "is_public": True,
        "is_deleted": False
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Community project not found"
        )
    
    # Increment view count
    await db.projects.update_one(
        {"project_id": project_id},
        {"$inc": {"view_count": 1}}
    )
    
    logger.info(
        "community_project_viewed",
        project_id=project_id,
        view_count=project.get("view_count", 0) + 1
    )
    
    return ProjectResponse(
        project_id=project["project_id"],
        name=project["name"],
        created_at=project["created_at"].isoformat(),
        last_updated=project["last_updated"].isoformat(),
        current_snapshot=project.get("current_snapshot"),
        summary=project.get("summary"),
        is_public=project.get("is_public", False),
        description=project.get("description"),
        screenshot_url=project.get("screenshot_url"),
        tags=project.get("tags", []),
        view_count=project.get("view_count", 0),
        fork_count=project.get("fork_count", 0)
    )


# ============================================================================
# PROJECT ROUTES
# ============================================================================
@router.get("/", response_model=List[ProjectResponse])
async def list_projects(user: Dict[str, Any] = Depends(require_auth)):
    """
    Get all projects for authenticated user.
    Returns list of projects (most recent first).
    """
    db = await get_database()
    
    projects = await db.projects.find(
        {
            "user_id": user["user_id"],
            "is_deleted": False
        }
    ).sort("created_at", -1).to_list(length=100)
    
    logger.info(
        "projects_listed",
        user_id=user["user_id"],
        project_count=len(projects)
    )
    
    return [
        ProjectResponse(
            project_id=p["project_id"],
            name=p["name"],
            created_at=p["created_at"].isoformat(),
            last_updated=p["last_updated"].isoformat(),
            current_snapshot=p.get("current_snapshot"),
            summary=p.get("summary"),
            is_public=p.get("is_public", False),
            description=p.get("description"),
            screenshot_url=p.get("screenshot_url"),
            tags=p.get("tags", []),
            view_count=p.get("view_count", 0),
            fork_count=p.get("fork_count", 0)
        )
        for p in projects
    ]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """
    Get single project details.
    """
    db = await get_database()
    
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"],
        "is_deleted": False
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    logger.info(
        "project_fetched",
        project_id=project_id,
        user_id=user["user_id"]
    )
    
    return ProjectResponse(
        project_id=project["project_id"],
        name=project["name"],
        created_at=project["created_at"].isoformat(),
        last_updated=project["last_updated"].isoformat(),
        current_snapshot=project.get("current_snapshot"),
        summary=project.get("summary"),
        is_public=project.get("is_public", False),
        description=project.get("description"),
        screenshot_url=project.get("screenshot_url"),
        tags=project.get("tags", []),
        view_count=project.get("view_count", 0),
        fork_count=project.get("fork_count", 0)
    )


@router.delete("/{project_id}")
async def delete_project(project_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """
    Soft delete a project.
    Marks project as deleted but preserves data.
    """
    db = await get_database()
    
    result = await db.projects.update_one(
        {
            "project_id": project_id,
            "user_id": user["user_id"]
        },
        {
            "$set": {"is_deleted": True}
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    logger.info(
        "project_deleted",
        project_id=project_id,
        user_id=user["user_id"]
    )
    
    return {"message": "Project deleted successfully"}


@router.get("/{project_id}/snapshots", response_model=List[SnapshotResponse])
async def list_snapshots(project_id: str, user: Dict[str, Any] = Depends(require_auth)):
    """
    Get all snapshots for a project.
    Returns snapshots sorted by timestamp (most recent first).
    """
    db = await get_database()
    
    # Verify project ownership
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"]
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    snapshots = await db.snapshots.find(
        {"project_id": project_id}
    ).sort("timestamp", -1).to_list(length=50)
    
    logger.info(
        "snapshots_listed",
        project_id=project_id,
        snapshot_count=len(snapshots)
    )
    
    return [
        SnapshotResponse(
            snapshot_id=s["snapshot_id"],
            timestamp=s["timestamp"].isoformat(),
            scp_version=s["scp_version"],
            label=s.get("label")
        )
        for s in snapshots
    ]


class RollbackRequest(BaseModel):
    """Rollback request"""
    snapshot_id: str = Field(..., description="Snapshot ID to rollback to")


@router.post("/{project_id}/rollback")
async def rollback_project(
    project_id: str,
    request: RollbackRequest,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    Rollback project to a specific snapshot.
    Updates current_snapshot reference.
    """
    db = await get_database()
    
    # Verify project ownership
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"]
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Verify snapshot exists
    snapshot = await db.snapshots.find_one({
        "snapshot_id": request.snapshot_id,
        "project_id": project_id
    })
    
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Snapshot not found"
        )
    
    # Update current snapshot
    await db.projects.update_one(
        {"project_id": project_id},
        {"$set": {"current_snapshot": request.snapshot_id}}
    )
    
    logger.info(
        "project_rolled_back",
        project_id=project_id,
        snapshot_id=request.snapshot_id,
        user_id=user["user_id"]
    )
    
    return {
        "message": "Project rolled back successfully",
        "snapshot_id": request.snapshot_id
    }


# ============================================================================
# FILE RETRIEVAL ROUTES
# ============================================================================
class FileResponse(BaseModel):
    """File content response"""
    path: str
    content: str
    language: str | None = None


class FilesResponse(BaseModel):
    """Files list response"""
    files: Dict[str, str]
    file_count: int


@router.get("/{project_id}/files", response_model=FilesResponse)
async def get_project_files(
    project_id: str, 
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    Get all files for a project from code_blobs collection.
    Returns dict of {file_path: file_content}.
    """
    db = await get_database()
    
    # Verify project ownership
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"],
        "is_deleted": False
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Fetch all files for project from code_blobs
    # file_id format is "{project_id}:{file_path}"
    blobs = await db.code_blobs.find({
        "file_id": {"$regex": f"^{project_id}:"}
    }).to_list(length=500)
    
    files = {}
    for blob in blobs:
        files[blob["path"]] = blob["content"]
    
    logger.info(
        "project_files_fetched",
        project_id=project_id,
        file_count=len(files),
        user_id=user["user_id"]
    )
    
    return FilesResponse(files=files, file_count=len(files))


# ============================================================================
# PREVIEW/SANDBOX ROUTES
# ============================================================================
class PreviewResponse(BaseModel):
    """Preview URL response"""
    preview_url: str | None
    status: str  # "active", "revived", "unavailable"
    message: str | None = None


class HeartbeatRequest(BaseModel):
    """Heartbeat request"""
    project_id: str


@router.post("/{project_id}/heartbeat")
async def send_heartbeat(
    project_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    Update sandbox activity timestamp.
    Prevents auto-cleanup while user is active.
    """
    from services.sandbox.e2b_manager import e2b_manager
    from datetime import datetime
    
    db = await get_database()
    
    # Verify ownership
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"]
    })
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Update E2B manager state
    if project_id in e2b_manager.last_activity:
        e2b_manager.last_activity[project_id] = datetime.utcnow()
        
    # Update DB session
    await db.sandbox_sessions.update_one(
        {"project_id": project_id},
        {"$set": {"last_active": datetime.utcnow()}}
    )
    
    return {"status": "ok"}


@router.get("/{project_id}/preview", response_model=PreviewResponse)
async def get_project_preview(
    project_id: str,
    user: Dict[str, Any] = Depends(require_auth)
):
    """
    Get preview URL for project sandbox.
    If sandbox has expired, automatically revives it from stored files.
    """
    from datetime import datetime
    from services.sandbox.e2b_manager import e2b_manager
    
    db = await get_database()
    
    # Verify project ownership
    project = await db.projects.find_one({
        "project_id": project_id,
        "user_id": user["user_id"],
        "is_deleted": False
    })
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Check existing sandbox session
    session = await db.sandbox_sessions.find_one({"project_id": project_id})
    
    # Try to use existing sandbox
    if session and session.get("sandbox_id"):
        # Check if sandbox is still alive
        is_alive = await e2b_manager.is_sandbox_alive(project_id)
        
        if not is_alive and session.get("sandbox_id"):
            # Try to reconnect to E2B sandbox
            reconnected = await e2b_manager.reconnect_sandbox(
                session["sandbox_id"], 
                project_id
            )
            is_alive = reconnected
        
        if is_alive:
            # Update last_active timestamp
            await db.sandbox_sessions.update_one(
                {"project_id": project_id},
                {"$set": {"last_active": datetime.utcnow()}}
            )
            
            return PreviewResponse(
                preview_url=session.get("preview_url"),
                status="active",
                message="Sandbox is running"
            )
    
    # Sandbox is dead or doesn't exist - need to revive
    logger.info(
        "reviving_sandbox",
        project_id=project_id
    )
    
    # Get files from database
    blobs = await db.code_blobs.find({
        "file_id": {"$regex": f"^{project_id}:"}
    }).to_list(length=500)
    
    if not blobs:
        return PreviewResponse(
            preview_url=None,
            status="unavailable",
            message="No files found - project may not have been generated yet"
        )
    
    files = {blob["path"]: blob["content"] for blob in blobs}
    
    try:
        # Create new sandbox
        sandbox_info = await e2b_manager.create_sandbox(project_id)
        
        # Determine preview mode (default to frontend_only for now for speed)
        # In future, can check project["summary"]["metadata"]["preview_mode"]
        # logic: if complexity is simple/moderate -> frontend_only
        # if complex -> fullstack (requires more credits)
        
        complexity = project.get("summary", {}).get("metadata", {}).get("complexity", "moderate")
        preview_mode = "frontend_only"
        
        # If user specifically requested fullstack (e.g. "real db"), we stick to fullstack
        # For now, we bias towards frontend_only for cost
        
        # Deploy files with mock injection if needed
        await e2b_manager.deploy_files(project_id, files, preview_mode=preview_mode)
        
        # Detect project type and install dependencies
        has_package_json = any("package.json" in path for path in files.keys())
        has_requirements = any("requirements.txt" in path for path in files.keys())
        
        if has_package_json:
            await e2b_manager.install_dependencies(project_id, {"react": "^18"}, preview_mode=preview_mode)
        elif has_requirements:
            await e2b_manager.install_dependencies(project_id, {"fastapi": "^0.100"})
        
        # Start server
        server_command = "npm run dev" if has_package_json else "python main.py"
        server_info = await e2b_manager.start_server(project_id, server_command)
        preview_url = server_info.get("preview_url")
        
        # Update or create sandbox session
        await db.sandbox_sessions.update_one(
            {"project_id": project_id},
            {"$set": {
                "sandbox_id": sandbox_info.get("sandbox_id"),
                "preview_url": preview_url,
                "status": "active",
                "last_active": datetime.utcnow(),
                "server_command": server_command
            }},
            upsert=True
        )
        
        logger.info(
            "sandbox_revived",
            project_id=project_id,
            preview_url=preview_url
        )
        
        return PreviewResponse(
            preview_url=preview_url,
            status="revived",
            message="Sandbox rebuilt from stored files"
        )
        
    except Exception as e:
        logger.exception(
            "sandbox_revival_failed",
            project_id=project_id,
            error=str(e)
        )
        
        # Update session with error status
        await db.sandbox_sessions.update_one(
            {"project_id": project_id},
            {"$set": {
                "status": "error",
                "last_active": datetime.utcnow()
            }},
            upsert=True
        )
        
        return PreviewResponse(
            preview_url=None,
            status="unavailable",
            message=f"Failed to create sandbox: {str(e)}"
        )
