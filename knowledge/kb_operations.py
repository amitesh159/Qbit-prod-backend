"""
Knowledge Base Operations
MongoDB-based project memory management following PRD flat-structure approach
"""
import re
import structlog
from typing import Dict, List, Any
from datetime import datetime
import uuid
from database.connection import get_database
from database.schemas import (
    ProjectSummary,
    ModuleModel,
    FileMetadataModel,
    FileAnchors,
    SnapshotModel,
    OperationLogModel
)
from utils.file_utils import calculate_file_hash, detect_language, count_lines, estimate_tokens

logger = structlog.get_logger(__name__)


async def save_project_summary(
    project_id: str,
    scp: Dict[str, Any]
) -> bool:
    """
    Save/update project summary from SCP.
    
    Args:
        project_id: Project identifier
        scp: Structured Context Protocol document
        
    Returns:
        bool: True if successful
    """
    db = await get_database()
    
    try:
        # Extract summary information from SCP
        # Handle project_overview being either a string or a dict
        project_overview = scp.get("project_overview", "")
        if isinstance(project_overview, dict):
            # Convert dict to string representation
            import json
            project_overview = json.dumps(project_overview, indent=2)
        elif not isinstance(project_overview, str):
            project_overview = str(project_overview)
        
        # Get tech stack, handling various formats
        tech_stack = scp.get("tech_stack", {})
        if isinstance(tech_stack, dict):
            stack_list = tech_stack.get("frontend", []) + tech_stack.get("backend", [])
        elif isinstance(tech_stack, list):
            stack_list = tech_stack
        else:
            stack_list = []
        
        # Get constraints, ensuring it's a list
        constraints = scp.get("constraints", [])
        if not isinstance(constraints, list):
            constraints = [str(constraints)] if constraints else []
        
        summary = ProjectSummary(
            architecture=project_overview,
            stack=stack_list,
            entry_points=[],  # Will be populated as files are analyzed
            major_modules=[],  # Will be populated from file structure
            constraints=constraints,
            token_estimate=len(str(scp)) // 4  # Rough estimate
        )
        
        # Update project with summary
        result = await db.projects.update_one(
            {"project_id": project_id},
            {
                "$set": {
                    "summary": summary.model_dump(),
                    "last_updated": datetime.utcnow()
                }
            }
        )
        
        logger.info(
            "project_summary_saved",
            project_id=project_id,
            modified=result.modified_count > 0
        )
        
        return result.modified_count > 0
        
    except Exception as e:
        logger.exception(
            "project_summary_save_failed",
            project_id=project_id,
            error=str(e)
        )
        return False


async def save_file_metadata(
    project_id: str,
    file_path: str,
    content: str
) -> bool:
    """
    Save/update file metadata in Knowledge Base.
    
    Args:
        project_id: Project identifier
        file_path: Relative path to file
        content: File content
        
    Returns:
        bool: True if successful
    """
    db = await get_database()
    
    try:
        # Calculate metadata
        file_hash = calculate_file_hash(content)
        # Detect programming language (for display purposes only)
        prog_language = detect_language(file_path)
        line_count = count_lines(content)
        token_estimate = estimate_tokens(content)
        
        # Extract anchors (enhanced implementation)
        anchors = _extract_code_anchors(content, file_path, prog_language)
        
        metadata = FileMetadataModel(
            project_id=project_id,
            path=file_path,
            language=prog_language,
            line_count=line_count,
            token_estimate=token_estimate,
            last_hash=file_hash,
            summary="",  # Can be enhanced with LLM-generated summaries
            anchors=anchors,
            dependencies=[],  # Can be extracted from imports
            last_modified=datetime.utcnow()
        )
        
        # Upsert file metadata
        # Note: We use simple upsert without text search language override
        # MongoDB text search languages don't include programming languages
        await db.files.update_one(
            {"project_id": project_id, "path": file_path},
            {"$set": metadata.model_dump()},
            upsert=True
        )
        
        logger.debug(
            "file_metadata_saved",
            project_id=project_id,
            file_path=file_path,
            language=prog_language
        )
        
        return True
        
    except Exception as e:
        logger.exception(
            "file_metadata_save_failed",
            project_id=project_id,
            file_path=file_path,
            error=str(e)
        )
        return False


async def retrieve_project_context(
    project_id: str,
    user_intent: str | None = None
) -> Dict[str, Any]:
    """
    Retrieve project context for follow-up requests.
    Returns project summary + relevant file metadata.
    
    Args:
        project_id: Project identifier
        user_intent: Optional user request for targeted retrieval
        
    Returns:
        Dict with project summary and relevant files
    """
    db = await get_database()
    
    try:
        # Get project with summary
        project = await db.projects.find_one({"project_id": project_id})
        
        if not project:
            logger.warning(
                "project_not_found_for_context",
                project_id=project_id
            )
            return {}
        
        # Get file metadata - use text search if user intent provided
        if user_intent:
            # Use MongoDB text search to find relevant files
            files = await db.files.find(
                {
                    "project_id": project_id,
                    "$text": {"$search": user_intent}
                },
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(20).to_list(length=20)
            
            logger.info(
                "context_retrieved_with_text_search",
                project_id=project_id,
                query=user_intent,
                relevant_files=len(files)
            )
        else:
            # Return all files if no intent specified
            files = await db.files.find(
                {"project_id": project_id}
            ).to_list(length=100)
        
        context = {
            "project_id": project_id,
            "name": project.get("name"),
            "summary": project.get("summary"),
            "files": [
                {
                    "path": f["path"],
                    "language": f["language"],
                    "line_count": f["line_count"],
                    "summary": f.get("summary", "")
                }
                for f in files
            ],
            "file_count": len(files)
        }
        
        logger.info(
            "project_context_retrieved",
            project_id=project_id,
            file_count=len(files)
        )
        
        return context
        
    except Exception as e:
        logger.exception(
            "project_context_retrieval_failed",
            project_id=project_id,
            error=str(e)
        )
        return {}


async def get_compressed_context(
    project_id: str,
    user_intent: str | None = None,
    max_tokens: int = 4000
) -> Dict[str, Any]:
    """
    Get COMPRESSED context for Central Hub SCP generation.
    
    This is optimized for follow-up modifications - gives Hub enough context
    to understand the codebase structure without including full file content.
    
    Context includes:
    - Project summary (architecture, stack)
    - File tree with purposes
    - Key anchors (exports, components) per file
    - Relevant files based on user intent (if provided)
    
    Args:
        project_id: Project identifier
        user_intent: Optional user request for targeted retrieval
        max_tokens: Approximate max tokens for context (default 4000)
        
    Returns:
        Compressed context dict for Central Hub
    """
    db = await get_database()
    
    try:
        project = await db.projects.find_one({"project_id": project_id})
        if not project:
            return {}
        
        # Get file metadata - targeted if intent provided
        if user_intent:
            files = await db.files.find(
                {
                    "project_id": project_id,
                    "$text": {"$search": user_intent}
                },
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(15).to_list(length=15)
        else:
            files = await db.files.find(
                {"project_id": project_id}
            ).to_list(length=50)
        
        # Build compressed file tree (no content, just structure)
        file_tree = []
        total_chars = 0
        char_limit = max_tokens * 4  # Rough char-to-token ratio
        
        for f in files:
            if total_chars > char_limit:
                file_tree.append("... (more files truncated)")
                break
                
            anchors = f.get("anchors", {})
            file_entry = {
                "path": f["path"],
                "purpose": f.get("summary", "")[:100],  # Truncate long summaries
                "exports": anchors.get("exports", [])[:5],  # Top 5 exports
                "components": anchors.get("components", [])[:5]  # Top 5 components
            }
            file_tree.append(file_entry)
            total_chars += len(str(file_entry))
        
        compressed = {
            "project_id": project_id,
            "name": project.get("name"),
            "summary": project.get("summary", {}),
            "file_count": len(files),
            "file_tree": file_tree,
            "relevant_to": user_intent if user_intent else "all"
        }
        
        logger.info(
            "compressed_context_generated",
            project_id=project_id,
            file_count=len(file_tree),
            char_count=total_chars
        )
        
        return compressed
        
    except Exception as e:
        logger.exception(
            "compressed_context_failed",
            project_id=project_id,
            error=str(e)
        )
        return {}



async def create_snapshot(
    project_id: str,
    scp_version: str,
    file_hashes: Dict[str, str],
    label: str | None = None
) -> str | None:
    """
    Create a project snapshot for version control.
    
    Args:
        project_id: Project identifier
        scp_version: SCP version (e.g., "1.0", "1.1")
        file_hashes: Dict of {file_path: hash}
        label: Optional snapshot label
        
    Returns:
        str | None: Snapshot ID if successful
    """
    db = await get_database()
    
    try:
        snapshot_id = str(uuid.uuid4())
        
        snapshot = SnapshotModel(
            snapshot_id=snapshot_id,
            project_id=project_id,
            timestamp=datetime.utcnow(),
            file_hashes=file_hashes,
            scp_version=scp_version,
            label=label
        )
        
        await db.snapshots.insert_one(snapshot.model_dump())
        
        # Update project current snapshot
        await db.projects.update_one(
            {"project_id": project_id},
            {"$set": {"current_snapshot": snapshot_id}}
        )
        
        logger.info(
            "snapshot_created",
            project_id=project_id,
            snapshot_id=snapshot_id,
            scp_version=scp_version
        )
        
        return snapshot_id
        
    except Exception as e:
        logger.exception(
            "snapshot_creation_failed",
            project_id=project_id,
            error=str(e)
        )
        return None


async def log_operation(
    project_id: str,
    operation_type: str,
    affected_files: List[str],
    diff_summary: str,
    patches: List[Dict[str, Any]],
    snapshot_id: str,
    user_prompt: str,
    agent: str,
    success: bool = True,
    error: str | None = None
) -> bool:
    """
    Log operation to audit trail.
    
    Args:
        project_id: Project identifier
        operation_type: "create" | "modify" | "delete"
        affected_files: List of file paths
        diff_summary: Human-readable change summary
        patches: JSON patch operations
        snapshot_id: Associated snapshot ID
        user_prompt: Original user request
        agent: Agent that executed
        success: Operation success status
        error: Error message if failed
        
    Returns:
        bool: True if logged successfully
    """
    db = await get_database()
    
    try:
        operation_id = str(uuid.uuid4())
        
        operation = OperationLogModel(
            project_id=project_id,
            operation_id=operation_id,
            timestamp=datetime.utcnow(),
            type=operation_type,
            affected_files=affected_files,
            diff_summary=diff_summary,
            patches=patches,
            snapshot_id=snapshot_id,
            user_prompt=user_prompt,
            agent=agent,
            success=success,
            error=error
        )
        
        await db.operation_log.insert_one(operation.model_dump())
        
        logger.info(
            "operation_logged",
            project_id=project_id,
            operation_id=operation_id,
            operation_type=operation_type
        )
        
        return True
        
    except Exception as e:
        logger.exception(
            "operation_log_failed",
            project_id=project_id,
            error=str(e)
        )
        return False


def _extract_code_anchors(content: str, file_path: str, language: str) -> FileAnchors:
    """
    Extract code anchors (imports, exports, functions, components) from file content.
    
    Args:
        content: File content
        file_path: File path for language detection
        language: Programming language
        
    Returns:
        FileAnchors with extracted code structures
    """
    imports = []
    exports = []
    functions = []
    components = []
    
    lines = content.split('\n')
    
    # Extract imports (JavaScript/TypeScript/Python)
    for line in lines:
        stripped = line.strip()
        
        # Python imports
        if stripped.startswith(('import ', 'from ')):
            imports.append(stripped)
        
        # JS/TS imports
        elif stripped.startswith('import '):
            imports.append(stripped.replace('\n', ''))
    
    # Extract exports and functions (JavaScript/TypeScript)
    if language in ['javascript', 'typescript', 'jsx', 'tsx']:
        # Export patterns
        export_patterns = [
            r'export\s+(?:default\s+)?(?:const|let|var|function|class)\s+(\w+)',
            r'export\s+\{([^}]+)\}',
            r'export\s+default\s+(\w+)'
        ]
        
        for pattern in export_patterns:
            matches = re.findall(pattern, content)
            exports.extend([m.strip() if isinstance(m, str) else m for m in matches])
        
        # Function patterns (including arrow functions)
        function_patterns = [
            r'(?:export\s+)?function\s+(\w+)',
            r'(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*\([^)]*\)\s*=>',
            r'(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*async\s*\([^)]*\)\s*=>'
        ]
        
        for pattern in function_patterns:
            matches = re.findall(pattern, content)
            functions.extend(matches)
        
        # React component patterns (PascalCase functions/classes)
        component_patterns = [
            r'(?:export\s+)?(?:default\s+)?(?:function|const)\s+([A-Z]\w+)',
            r'(?:export\s+)?(?:default\s+)?class\s+([A-Z]\w+)\s+extends\s+(?:React\.)?Component'
        ]
        
        for pattern in component_patterns:
            matches = re.findall(pattern, content)
            components.extend(matches)
    
    # Extract Python functions/classes
    elif language == 'python':
        # Function definitions
        function_matches = re.findall(r'def\s+(\w+)\s*\(', content)
        functions.extend(function_matches)
        
        # Class definitions (treat as components)
        class_matches = re.findall(r'class\s+(\w+)\s*[:\(]', content)
        components.extend(class_matches)
    
    # Remove duplicates and return
    return FileAnchors(
        imports=list(set(imports)),
        exports=list(set(exports)),
        functions=list(set(functions)),
        components=list(set(components))
    )
