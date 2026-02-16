"""
Code Generation WebSocket Route
Main orchestration endpoint using Central Hub and Full Stack Agent
"""
import uuid
import json
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from datetime import datetime
import traceback

from database.connection import get_database
from database.schemas import ProjectModel, SCPVersionModel
from hub import get_central_hub
from agents.fullstack_agent import get_fullstack_agent
from credits.credit_manager import deduct_credits, rollback_credits, check_credits
from websocket.manager import manager
from config.settings import settings
from schemas.scp import CentralHubOutput, SCPSchema
from schemas.agent import AgentOutputSchema, FileSchema
from auth.jwt_utils import decode_access_token
from services.sandbox.e2b_manager import e2b_manager

logger = structlog.get_logger(__name__)

try:
    from utils.debug_logger import dlog
except ImportError:
    def dlog(*args, **kwargs): pass

router = APIRouter(tags=["code_generation"])


@router.websocket("/ws/generate")
async def websocket_code_generation(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket endpoint for real-time code generation.
    Handles complete orchestration flow:
    1. Intent classification
    2. SCP generation
    3. Credit deduction
    4. Agent execution
    5. Progress updates via WebSocket
    
    Args:
        token: JWT token for authentication (query param)
    """
    # Authenticate user
    payload = decode_access_token(token)
    
    if not payload:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    user_id = payload.get("user_id")
    
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token payload")
        return
    
    # Connect WebSocket
    connection_id = await manager.connect(websocket, user_id)
    
    try:
        # Main message loop
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            message_type = data.get("type")
            
            if message_type == "generate_code":
                await handle_code_generation(user_id, data)
            
            elif message_type == "modify_code":
                await handle_code_modification(user_id, data)
            
            elif message_type == "ping":
                await manager.send_message(user_id, {
                    "type": "pong",
                    "payload": {"timestamp": datetime.utcnow().isoformat()}
                })
            
            else:
                await manager.send_error(
                    user_id,
                    f"Unknown message type: {message_type}",
                    "UNKNOWN_MESSAGE_TYPE"
                )
    
    except WebSocketDisconnect:
        logger.info(
            "websocket_disconnected",
            user_id=user_id,
            connection_id=connection_id
        )
        manager.disconnect(user_id)
    
    except Exception as e:
        logger.exception(
            "websocket_error",
            user_id=user_id,
            error=str(e)
        )
        await manager.send_error(
            user_id,
            "Internal server error",
            "INTERNAL_ERROR"
        )
        manager.disconnect(user_id)


async def handle_code_generation(user_id: str, data: dict):
    """
    Handle new project code generation request.
    Complete orchestration flow with progress updates.
    """
    user_prompt = data.get("payload", {}).get("prompt")
    
    if not user_prompt:
        await manager.send_error(user_id, "No prompt provided", "INVALID_REQUEST")
        return
    
    logger.info(
        "code_generation_started",
        user_id=user_id,
        prompt_length=len(user_prompt)
    )
    
    db = await get_database()
    project_id = str(uuid.uuid4())
    
    try:
        # ==================================================================
        # STAGE 1: ORCHESTRATION (Central Hub)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "orchestration", 10,
            "Analyzing your request..."
        )
        
        # Send real-time planning updates
        await manager.send_scp_planning(
            user_id, "analyzing_intent",
            "Understanding your requirements"
        )
        
        # Notify frontend of project ID immediately
        await manager.send_project_created(user_id, project_id)
        
        # Call Hub with LangChain structured output
        orchestration_result: CentralHubOutput = await get_central_hub().process_message(
            user_message=user_prompt,
            discussion_mode=False,
            project_id=None,  # No existing project for new generation
            user_id=user_id
        )
        
        # Type-safe access to Pydantic object
        intent = orchestration_result.intent
        dlog("Central Hub", f"Intent: {intent}, Complexity: {orchestration_result.complexity}")
        
        # Handle non-code-generation intents
        if intent != "code_generation":
            await manager.send_message(user_id, {
                "type": "response",
                "payload": {
                    "intent": intent,
                    "response": orchestration_result.response,
                    "suggestions": []  # Can add to schema if needed
                }
            })
            return
        
        # Extract SCP and complexity (type-safe)
        scp: SCPSchema = orchestration_result.scp
        complexity = orchestration_result.complexity or "moderate"
        
        # Calculate credits based on complexity
        credits_map = {"simple": 10, "moderate": 20, "complex": 35}
        credits_required = credits_map.get(complexity, 20)
        
        if not scp:
            dlog("Central Hub", "SCP generation failed", error=True)
            await manager.send_error(
                user_id,
                "Failed to generate project specification",
                "SCP_GENERATION_FAILED"
            )
            return
        
        dlog("Central Hub", f"SCP ready, {credits_required} credits needed")
        
        # Send SCP details to frontend for transparency
        # Convert Pydantic SCP to dict for WebSocket serialization
        scp_dict = scp.model_dump() if hasattr(scp, 'model_dump') else scp
        await manager.send_scp_generated(
            user_id=user_id,
            scp=scp_dict,
            summary=scp.project_overview if hasattr(scp, 'project_overview') else "Project specification generated",
            complexity=complexity,
            credits_required=credits_required,
            file_count=len(scp.features) if hasattr(scp, 'features') else 0
        )
        
        # ==================================================================
        # STAGE 2: CREDIT DEDUCTION
        # ==================================================================
        await manager.send_progress_update(
            user_id, "credit_check", 25,
            f"Validating credits ({credits_required} required)..."
        )
        
        credit_deducted = await deduct_credits(
            user_id, credits_required,
            f"Project generation: {complexity}",
            project_id
        )
        
        if not credit_deducted:
            await manager.send_error(
                user_id,
                f"Insufficient credits. Required: {credits_required}",
                "INSUFFICIENT_CREDITS",
                retry_allowed=False
            )
            return
        
        # ==================================================================
        # STAGE 3: AGENT EXECUTION (Full Stack Agent with Streaming)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "code_generation", 40,
            "Generating code files..."
        )
        
        # Send agent planning start
        await manager.send_agent_planning(
            user_id=user_id,
            agent_name="fullstack_agent",
            planning_step="Analyzing project architecture",
            progress=42
        )
        
        try:
            # Use non-streaming execute() for validated Pydantic output
            # No manual JSON parsing needed — returns AgentOutputSchema
            scp_dict = scp.model_dump() if hasattr(scp, 'model_dump') else scp
            agent_output: AgentOutputSchema = await get_fullstack_agent().execute(
                scp=scp_dict,
                task_type="new_project",
                project_id=project_id
            )
            
            dlog("FullStack Agent", f"Generated {len(agent_output.files)} files (structured output)")
            
        except Exception as e:
            # Rollback credits on failure
            dlog("Agent", f"Agent execution failed: {str(e)}", error=True)
            await rollback_credits(user_id, credits_required, "Agent execution failed")
            raise e
        
        # Convert Pydantic FileSchema list to dict for DB and E2B compatibility
        files = {f.path: f.content for f in agent_output.files}
        dependencies = agent_output.dependencies
        setup_instructions = agent_output.instructions or ""
        
        dlog("FullStack Agent", f"Generated {len(files)} files")
        
        # CRITICAL: Send parsed files to frontend for display
        # The raw tokens don't have structure, but now we have parsed files
        for file_path, file_content in files.items():
            # Detect language from extension
            ext = file_path.split(".")[-1].lower() if "." in file_path else ""
            lang_map = {
                "ts": "typescript", "tsx": "typescript",
                "js": "javascript", "jsx": "javascript",
                "json": "json", "css": "css", "html": "html",
                "md": "markdown", "py": "python"
            }
            language = lang_map.get(ext, "text")
            
            # Send complete file with is_complete=True
            await manager.send_code_token(
                user_id=user_id,
                token=file_content,
                file_path=file_path,
                language=language
            )
            # Mark file as complete
            await manager.send_message(user_id, {
                "type": "code_token",
                "payload": {
                    "file_path": file_path,
                    "token": "",
                    "is_complete": True,
                    "language": language
                }
            })
        
        if not files:
            # Rollback credits
            dlog("FullStack Agent", "No files generated", error=True)
            await rollback_credits(user_id, credits_required, "No files generated")
            await manager.send_error(
                user_id,
                "Agent failed to generate code",
                "AGENT_EXECUTION_FAILED"
            )
            return
        
        # ==================================================================
        # STAGE 4: SAVE TO DATABASE
        # ==================================================================
        dlog("GenerationRoutes", "Starting Stage 4: Database Save")
        await manager.send_progress_update(
            user_id, "database_save", 70,
            "Saving project to database..."
        )
        
        # Create project
        project_name = scp.project_overview[:50] if hasattr(scp, 'project_overview') else "Untitled Project"
        
        project = ProjectModel(
            project_id=project_id,
            user_id=user_id,
            name=project_name,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            summary=None  # Will be updated by KB later
        )

        dlog("GenerationRoutes", f"Saving project model {project_id}")
        await db.projects.insert_one(project.model_dump())
        
        # Save SCP version
        scp_version = SCPVersionModel(
            project_id=project_id,
            version="1.0",
            scp_document=scp.model_dump() if hasattr(scp, 'model_dump') else scp,
            created_at=datetime.utcnow()
        )
        
        await db.scp_versions.insert_one(scp_version.model_dump())
        
        # ==================================================================
        # STAGE 4.5: UPDATE KNOWLEDGE BASE
        # ==================================================================
        dlog("KB", "Updating Knowledge Base with project metadata")
        
        try:
            from knowledge.kb_operations import (
                save_project_summary,
                save_file_metadata,
                create_snapshot,
                log_operation
            )
            
            # Save project summary from SCP
            await save_project_summary(project_id, scp.model_dump() if hasattr(scp, 'model_dump') else scp)
            dlog("KB", "Saved project summary")
            
            # Save file metadata for all generated files
            file_paths_saved = []
            for file_path, content in files.items():
                await save_file_metadata(project_id, file_path, content)
                file_paths_saved.append(file_path)
            dlog("KB", f"Saved metadata for {len(file_paths_saved)} files")
            
            # Create initial snapshot for version control
            from utils.file_utils import calculate_file_hash
            file_hashes = {
                path: calculate_file_hash(content)
                for path, content in files.items()
            }
            snapshot_id = await create_snapshot(
                project_id=project_id,
                scp_version="1.0",
                file_hashes=file_hashes,
                label="Initial project creation"
            )
            dlog("KB", f"Created snapshot: {snapshot_id}")
            
            # Log operation to audit trail
            await log_operation(
                project_id=project_id,
                operation_type="create",
                affected_files=file_paths_saved,
                diff_summary=f"Created {project_name} with {len(files)} files",
                patches=[],  # No patches for new project
                snapshot_id=snapshot_id,
                user_prompt=user_prompt,
                agent="fullstack_agent",
                success=True
            )
            dlog("KB", "Logged operation to audit trail")
            
        except ImportError:
            logger.warning("kb_operations_not_available_skipping")
        except Exception as kb_error:
            logger.exception("kb_update_failed", error=str(kb_error))
            # Don't fail the whole request if KB fails
        
        # Save files to code_blobs
        file_hashes = {}
        dlog("GenerationRoutes", f"Saving {len(files)} code blobs")
        for file_path, content in files.items():
            await db.code_blobs.insert_one({
                "file_id": f"{project_id}:{file_path}",
                "path": file_path,
                "content": content,
                "compressed": False
            })
            

        
        # ==================================================================
        # STAGE 5: E2B SANDBOX DEPLOYMENT
        # ==================================================================
        dlog("GenerationRoutes", "Starting Stage 5: E2B Deployment")
        await manager.send_progress_update(
            user_id, "sandbox_deployment", 85,
            "Deploying to E2B sandbox..."
        )
        
        preview_url = "/preview/placeholder"  # Default fallback
        
        try:
            from services.sandbox.e2b_manager import e2b_manager
            import asyncio
            
            dlog("E2B", "Starting sandbox creation...")
            
            # Create sandbox with timeout
            try:
                async with asyncio.timeout(60):  # 60 second timeout for creation
                    sandbox_info = await e2b_manager.create_sandbox(project_id)
                    dlog("E2B", f"Sandbox created: {sandbox_info.get('sandbox_id', 'unknown')}")
            except asyncio.TimeoutError:
                dlog("E2B", "Sandbox creation timed out after 60s", error=True)
                raise Exception("Sandbox creation timed out")
            
            # Deploy files with timeout
            try:
                async with asyncio.timeout(60):
                    await e2b_manager.deploy_files(
                        project_id=project_id, 
                        files=files,
                        websocket_manager=manager,
                        user_id=user_id
                    )
                    dlog("E2B", "Files deployed successfully")
            except asyncio.TimeoutError:
                dlog("E2B", "File deployment timed out", error=True)
                raise Exception("File deployment timed out")
            # Inject fallback package.json if missing - CRITICAL ROBUSTNESS STEP
            # Ensures npm install never fails due to missing manifest
            await e2b_manager.inject_package_json(
                project_id=project_id,
                files=files,
                websocket_manager=manager,
                user_id=user_id
            )

            # Install dependencies if present
            if dependencies:
                try:
                    async with asyncio.timeout(120):  # 2 min for npm install
                        await e2b_manager.install_dependencies(
                            project_id=project_id, 
                            preview_mode="fullstack",
                            websocket_manager=manager,
                            user_id=user_id
                        )
                        dlog("E2B", "Dependencies installed")
                except asyncio.TimeoutError:
                    dlog("E2B", "Dependency installation timed out", error=True)
                    # Continue anyway - server might still start
            
            # Start development server
            try:
                async with asyncio.timeout(60):
                    server_info = await e2b_manager.start_servers(
                        project_id=project_id,
                        preview_mode="fullstack",
                        websocket_manager=manager,
                        user_id=user_id
                    )
                    preview_url = server_info.get("preview_url", preview_url)
                    dlog("E2B", f"Server started: {preview_url}")
            except asyncio.TimeoutError:
                dlog("E2B", "Server start timed out", error=True)
            
            logger.info(
                "sandbox_deployed",
                project_id=project_id,
                preview_url=preview_url
            )
            
            # Save sandbox session for persistence
            await db.sandbox_sessions.update_one(
                {"project_id": project_id},
                {"$set": {
                    "session_id": str(uuid.uuid4()),  # Generate unique session ID
                    "sandbox_id": sandbox_info.get("sandbox_id"),
                    "preview_url": preview_url,
                    "status": "active",
                    "last_active": datetime.utcnow(),
                    "server_command": "npm run dev",
                    "port": 3000,
                    "preview_mode": "fullstack",  # Track for auto-reconnection
                    "created_at": datetime.utcnow()
                }},
                upsert=True
            )
            
        except Exception as e:
            logger.error(
                "sandbox_deployment_failed",
                project_id=project_id,
                error=str(e)
            )
            # Continue even if sandbox fails - files are still saved
        
        # ==================================================================
        # STAGE 6: COMPLETION
        # ==================================================================
        await manager.send_progress_update(
            user_id, "complete", 100,
            "Code generation complete!"
        )
        
        await manager.send_completion(
            user_id,
            project_id=project_id,
            preview_url=preview_url,  # E2B sandbox URL
            scp_version="1.0",
            credits_used=credits_required
        )
        
        logger.info(
            "code_generation_completed",
            user_id=user_id,
            project_id=project_id,
            file_count=len(files),
            credits_used=credits_required
        )
    
    except Exception as e:
        logger.exception(
            "code_generation_failed",
            user_id=user_id,
            project_id=project_id,
            error=str(e)
        )
        await manager.send_error(
            user_id,
            "Code generation failed. Please try again.",
            "GENERATION_ERROR",
            retry_allowed=True
        )


async def handle_code_modification(user_id: str, data: dict):
    """
    Handle project modification request (follow-up).
    Uses compressed context and hot reload for minimal diff updates.
    """
    payload = data.get("payload", {})
    user_prompt = payload.get("prompt")
    project_id = payload.get("project_id")
    
    if not user_prompt or not project_id:
        await manager.send_error(user_id, "Missing prompt or project_id", "INVALID_REQUEST")
        return
    
    logger.info(
        "code_modification_started",
        user_id=user_id,
        project_id=project_id
    )
    
    db = await get_database()
    
    try:
        # Verify project ownership
        project = await db.projects.find_one({
            "project_id": project_id,
            "user_id": user_id
        })
        
        if not project:
            await manager.send_error(user_id, "Project not found", "PROJECT_NOT_FOUND")
            return
        
        # ==================================================================
        # STAGE 1: GET COMPRESSED CONTEXT (optimized for Hub)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "orchestration", 15,
            "Loading project context..."
        )
        
        from knowledge.kb_operations import get_compressed_context
        compressed_context = await get_compressed_context(
            project_id=project_id,
            user_intent=user_prompt,
            max_tokens=4000
        )
        
        # Get full file content for affected files only
        files = {}
        async for blob in db.code_blobs.find({"file_id": {"$regex": f"^{project_id}:"}}):
            files[blob["path"]] = blob["content"]
        
        project_context = {
            "compressed": compressed_context,
            "file_paths": list(files.keys()),
            "file_count": len(files)
        }
        
        # ==================================================================
        # STAGE 2: ORCHESTRATION (get incremental SCP)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "orchestration", 25,
            "Analyzing modification request..."
        )
        
        # Call Hub with LangChain structured output
        result: CentralHubOutput = await get_central_hub().process_message(
            user_message=user_prompt,
            discussion_mode=False,
            project_id=project_id,
            user_id=user_id
        )
        
        # Type-safe access to Pydantic object
        intent = result.intent
        
        if intent != "follow_up":
            # Not a modification, handle as conversation
            await manager.send_message(user_id, {
                "type": "response",
                "payload": {
                    "intent": intent,
                    "response": result.response,
                    "suggestions": []
                }
            })
            return
        
        scp = result.scp
        complexity = result.complexity or "moderate"
        credits_map = {"simple": 8, "moderate": 15, "complex": 25}
        credits_required = credits_map.get(complexity, 15)
        
        # ==================================================================
        # STAGE 3: CREDIT CHECK
        # ==================================================================
        credit_deducted = await deduct_credits(
            user_id, credits_required,
            f"Modification: {project.get('name')}",
            project_id
        )
        
        if not credit_deducted:
            await manager.send_error(
                user_id,
                f"Insufficient credits. Required: {credits_required}",
                "INSUFFICIENT_CREDITS",
                retry_allowed=False
            )
            return
        
        # ==================================================================
        # STAGE 4: AGENT EXECUTION (minimal diff)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "code_generation", 50,
            "Generating modifications..."
        )
        
        # Include existing file content for affected files
        # SCP existing_context contains affected_files if present
        affected_paths = scp.existing_context.get("affected_files", []) if scp and scp.existing_context else []
        existing_content = {path: files.get(path, "") for path in affected_paths}
        
        # Convert SCP to dict for agent consumption and inject existing files
        scp_dict = scp.model_dump() if hasattr(scp, 'model_dump') else scp
        scp_dict["existing_files"] = existing_content
        
        try:
            # Use refactored agent with tools for follow-up context
            agent_output: AgentOutputSchema = await get_fullstack_agent().execute(
                scp=scp_dict,
                task_type="follow_up",
                project_id=project_id,
                use_tools=True  # Enable tools for codebase context
            )
            
        except Exception as e:
            await rollback_credits(user_id, credits_required, "Agent execution failed")
            raise e
        
        # Convert Pydantic FileSchema list to dict
        modified_files = {f.path: f.content for f in agent_output.files}
        
        # ==================================================================
        # STAGE 5: HOT RELOAD (apply changes to existing sandbox)
        # ==================================================================
        await manager.send_progress_update(
            user_id, "sandbox_update", 75,
            "Applying changes with hot reload..."
        )
        
        # Check if sandbox exists
        preview_url = None
        if project_id in e2b_manager.active_sandboxes:
            # Hot reload - just update changed files
            await e2b_manager.deploy_files(
                project_id=project_id,
                files=modified_files,
                websocket_manager=manager,
                user_id=user_id
            )
            preview_url = e2b_manager.get_preview_url(project_id)
            logger.info("hot_reload_applied", project_id=project_id, file_count=len(modified_files))
        else:
            # No existing sandbox - create new one
            logger.info("creating_new_sandbox_for_modification", project_id=project_id)
            # Full files = existing + modified
            all_files = {**files, **modified_files}
            
            await e2b_manager.create_sandbox(project_id)
            await e2b_manager.deploy_files(project_id, all_files, manager, user_id)
            await e2b_manager.install_dependencies(project_id, None, manager, user_id)
            server_result = await e2b_manager.start_servers(project_id, "fullstack", manager, user_id)
            preview_url = server_result.get("preview_url")
        
        # ==================================================================
        # STAGE 6: UPDATE DATABASE
        # ==================================================================
        for file_path, content in modified_files.items():
            file_id = f"{project_id}:{file_path}"
            await db.code_blobs.update_one(
                {"file_id": file_id},
                {"$set": {"content": content, "updated_at": datetime.utcnow()}},
                upsert=True
            )
        
        # ==================================================================
        # COMPLETE
        # ==================================================================
        await manager.send_message(user_id, {
            "type": "generation_complete",
            "payload": {
                "project_id": project_id,
                "preview_url": preview_url,
                "files_modified": list(modified_files.keys()),
                "scp_version": scp.version if hasattr(scp, 'version') else "1.1",
                "hot_reload": project_id in e2b_manager.active_sandboxes
            }
        })
        
        logger.info(
            "code_modification_complete",
            project_id=project_id,
            files_modified=len(modified_files)
        )
        
    except Exception as e:
        logger.exception(
            "code_modification_failed",
            user_id=user_id,
        )
        await manager.send_error(
            user_id,
            "Modification failed",
            "MODIFICATION_ERROR",
            retry_allowed=True
        )
