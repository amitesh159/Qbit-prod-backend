"""
Code Generation WebSocket Route - Agentic Orchestration
Uses Central Hub AgentStrategy to drive multi-call agent execution (QAP).
"""
import uuid
import asyncio
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from datetime import datetime
from typing import Dict, List, Optional

from database.connection import get_database
from database.schemas import ProjectModel, SCPVersionModel
from hub import get_central_hub
from agents.fullstack_agent import get_fullstack_agent
from agents.fullstack_agent.fullstack_agent import _merge_agent_outputs
from credits.credit_manager import deduct_credits, rollback_credits
from websocket.manager import manager
from schemas.scp import CentralHubOutput, SCPSchema
from schemas.agent import AgentOutputSchema, FileOperation
from auth.jwt_utils import decode_access_token
from services.sandbox.e2b_manager import e2b_manager

logger = structlog.get_logger(__name__)

try:
    from utils.debug_logger import dlog
except ImportError:
    def dlog(*args, **kwargs): pass

router = APIRouter(tags=["code_generation"])


# ============================================================================
# QAP OPERATION EXECUTOR
# ============================================================================

async def _execute_operations(
    operations: List[FileOperation],
    existing_files: Dict[str, str]
) -> Dict[str, str]:
    """
    Execute QAP FileOperation list and return merged file dict.

    - write:  Full content replace (new file or overwrite)
    - modify: If search+replace defined: substring replace. Otherwise use content as full replacement.
    - delete: Remove from dict
    """
    result = dict(existing_files)

    for op in operations:
        path = op.path
        if op.operation == "write":
            result[path] = op.content or ""
        elif op.operation == "modify":
            if op.search and op.replace is not None:
                # Targeted search/replace inside existing file
                existing = result.get(path, "")
                result[path] = existing.replace(op.search, op.replace, 1)
            elif op.content:
                # Fallback: treat content as full replacement
                result[path] = op.content
        elif op.operation == "delete":
            result.pop(path, None)

    return result


def _check_npm_install_needed(
    operations: List[FileOperation],
    new_packages: List[str]
) -> bool:
    """
    Decide whether npm install needs to run after applying operations.

    True if:
    - Any new_packages declared by agent
    - A package.json file was written/modified
    """
    if new_packages:
        return True
    for op in operations:
        if op.path.endswith("package.json") and op.operation in ("write", "modify"):
            return True
    return False


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@router.websocket("/ws/generate")
async def websocket_code_generation(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket endpoint for real-time code generation.
    Handles complete orchestration via Central Hub AgentStrategy.
    """
    payload = decode_access_token(token)
    if not payload:
        await websocket.close(code=1008, reason="Invalid token")
        return

    user_id = payload.get("user_id")
    if not user_id:
        await websocket.close(code=1008, reason="Invalid token payload")
        return

    connection_id = await manager.connect(websocket, user_id)

    try:
        while True:
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
        logger.info("websocket_disconnected", user_id=user_id, connection_id=connection_id)
        manager.disconnect(user_id)

    except Exception as e:
        logger.exception("websocket_error", user_id=user_id, error=str(e))
        await manager.send_error(user_id, "Internal server error", "INTERNAL_ERROR")
        manager.disconnect(user_id)


# ============================================================================
# NEW PROJECT GENERATION
# ============================================================================

async def handle_code_generation(user_id: str, data: dict):
    """
    Handle new project code generation.

    Flow:
    1. Hub classification + AgentStrategy
    2. Credit deduction
    3. Multi-call agent loop (Hub-scoped, QAP output)
    4. QAP operation execution → files dict
    5. DB save
    6. E2B sandbox deploy
    7. Completion event
    """
    user_prompt = data.get("payload", {}).get("prompt")
    if not user_prompt:
        await manager.send_error(user_id, "No prompt provided", "INVALID_REQUEST")
        return

    logger.info("code_generation_started", user_id=user_id, prompt_length=len(user_prompt))

    db = await get_database()
    project_id = str(uuid.uuid4())

    try:
        # ======================================================================
        # STAGE 1: HUB ORCHESTRATION
        # ======================================================================
        await manager.send_progress_update(user_id, "orchestration", 10, "Analyzing your request...")
        await manager.send_scp_planning(user_id, "analyzing_intent", "Understanding your requirements")
        await manager.send_project_created(user_id, project_id)

        orchestration_result: CentralHubOutput = await get_central_hub().process_message(
            user_message=user_prompt,
            discussion_mode=False,
            project_id=None,
            user_id=user_id
        )

        intent = orchestration_result.intent
        dlog("Hub", f"Intent: {intent}, Complexity: {orchestration_result.complexity}")

        if intent != "code_generation":
            await manager.send_message(user_id, {
                "type": "response",
                "payload": {
                    "intent": intent,
                    "response": orchestration_result.response,
                }
            })
            return

        scp: SCPSchema = orchestration_result.scp
        complexity = orchestration_result.complexity or "moderate"
        agent_strategy = orchestration_result.agent_strategy  # Hub-planned strategy

        if not scp:
            await manager.send_error(user_id, "Failed to generate project specification", "SCP_GENERATION_FAILED")
            return

        # Send SCP to frontend for transparency
        scp_dict = scp.model_dump() if hasattr(scp, "model_dump") else scp
        await manager.send_scp_generated(
            user_id=user_id,
            scp=scp_dict,
            summary=getattr(scp, "project_overview", "Project specification generated"),
            complexity=complexity,
            credits_required=0,  # Updated below
            file_count=len(getattr(scp, "features", []))
        )

        # ======================================================================
        # STAGE 2: CREDIT DEDUCTION
        # ======================================================================
        credits_map = {"simple": 10, "moderate": 20, "complex": 35}
        credits_required = credits_map.get(complexity, 20)

        await manager.send_progress_update(user_id, "credit_check", 25,
                                           f"Validating credits ({credits_required} required)...")

        credit_deducted = await deduct_credits(
            user_id, credits_required, f"Project generation: {complexity}", project_id
        )
        if not credit_deducted:
            await manager.send_error(
                user_id,
                f"Insufficient credits. Required: {credits_required}",
                "INSUFFICIENT_CREDITS",
                retry_allowed=False
            )
            return

        # ======================================================================
        # STAGE 3: MULTI-CALL AGENT EXECUTION (Hub-driven scopes)
        # ======================================================================
        await manager.send_progress_update(user_id, "code_generation", 40, "Generating code...")

        # Determine calls from Hub strategy; fallback to single call
        calls = []
        key_concerns: List[str] = []

        if agent_strategy and hasattr(agent_strategy, "calls") and agent_strategy.calls:
            calls = agent_strategy.calls
            key_concerns = getattr(agent_strategy, "key_concerns", [])
        else:
            # Fallback: single call, broad scope
            from schemas.scp import AgentCallScope
            calls = [AgentCallScope(
                call_number=1,
                scope="Generate all required files for this project",
                purpose="Full project generation"
            )]

        agent_results: List[AgentOutputSchema] = []
        context_from_previous: Optional[str] = None
        agent = get_fullstack_agent()

        for i, call_scope in enumerate(calls):
            call_num = i + 1
            progress = 40 + int(30 * (i / len(calls)))
            await manager.send_progress_update(
                user_id, "code_generation", progress,
                f"Agent call {call_num}/{len(calls)}: {getattr(call_scope, 'purpose', 'Generating...')}..."
            )

            await manager.send_message(user_id, {
                "type": "agent_started",
                "payload": {
                    "call_number": call_num,
                    "total_calls": len(calls),
                    "scope": getattr(call_scope, "scope", ""),
                    "purpose": getattr(call_scope, "purpose", "")
                }
            })

            try:
                result: AgentOutputSchema = await agent.execute_scoped(
                    scp=scp_dict,
                    task_type="new_project",
                    scope=getattr(call_scope, "scope", "Generate all required files"),
                    call_number=call_num,
                    context_from_previous=context_from_previous,
                    key_concerns=key_concerns,
                    project_id=project_id
                )

                agent_results.append(result)

                # Build context summary for next call
                context_from_previous = agent._format_operations_as_context(result)

                # Stream file paths to frontend
                for op in result.file_operations:
                    if op.operation in ("write", "modify"):
                        ext = op.path.split(".")[-1].lower() if "." in op.path else ""
                        lang_map = {
                            "ts": "typescript", "tsx": "typescript",
                            "js": "javascript", "jsx": "javascript",
                            "json": "json", "css": "css", "html": "html",
                            "md": "markdown", "py": "python"
                        }
                        language = lang_map.get(ext, "text")
                        await manager.send_code_token(
                            user_id=user_id,
                            token=op.content or "",
                            file_path=op.path,
                            language=language
                        )
                        await manager.send_message(user_id, {
                            "type": "code_token",
                            "payload": {"file_path": op.path, "token": "", "is_complete": True, "language": language}
                        })

                await manager.send_message(user_id, {
                    "type": "agent_call_complete",
                    "payload": {
                        "call_number": call_num,
                        "files_in_call": len(result.file_operations),
                        "new_packages": result.new_packages
                    }
                })

            except Exception as e:
                logger.exception("agent_call_failed", call_number=call_num, error=str(e))
                await rollback_credits(user_id, credits_required, f"Agent call {call_num} failed")
                raise e

        # ======================================================================
        # STAGE 4: MERGE RESULTS + EXECUTE QAP OPERATIONS
        # ======================================================================
        merged: AgentOutputSchema = _merge_agent_outputs(*agent_results)

        # Execute QAP operations → build files dict
        files: Dict[str, str] = await _execute_operations(merged.file_operations, existing_files={})

        # Determine if npm install is needed  
        needs_npm = _check_npm_install_needed(merged.file_operations, merged.new_packages)

        if not files:
            await rollback_credits(user_id, credits_required, "No files generated")
            await manager.send_error(user_id, "Agent failed to generate code", "AGENT_EXECUTION_FAILED")
            return

        # ======================================================================
        # STAGE 5: SAVE TO DATABASE
        # ======================================================================
        await manager.send_progress_update(user_id, "database_save", 72, "Saving project...")

        project_name = getattr(scp, "project_overview", "Untitled Project")[:50]

        project = ProjectModel(
            project_id=project_id,
            user_id=user_id,
            name=project_name,
            created_at=datetime.utcnow(),
            last_updated=datetime.utcnow(),
            summary=None
        )
        await db.projects.insert_one(project.model_dump())

        scp_version = SCPVersionModel(
            project_id=project_id,
            version="1.0",
            scp_document=scp_dict,
            created_at=datetime.utcnow()
        )
        await db.scp_versions.insert_one(scp_version.model_dump())

        # Save code blobs
        for file_path, content in files.items():
            await db.code_blobs.insert_one({
                "file_id": f"{project_id}:{file_path}",
                "path": file_path,
                "content": content,
                "compressed": False
            })

        # Update Knowledge Base
        try:
            from knowledge.kb_operations import save_project_summary, save_file_metadata, create_snapshot, log_operation
            from utils.file_utils import calculate_file_hash

            await save_project_summary(project_id, scp_dict)

            for file_path, content in files.items():
                await save_file_metadata(project_id, file_path, content)

            file_hashes = {path: calculate_file_hash(content) for path, content in files.items()}
            snapshot_id = await create_snapshot(
                project_id=project_id, scp_version="1.0", file_hashes=file_hashes,
                label="Initial project creation"
            )
            await log_operation(
                project_id=project_id, operation_type="create",
                affected_files=list(files.keys()),
                diff_summary=f"Created {project_name} with {len(files)} files",
                patches=[], snapshot_id=snapshot_id,
                user_prompt=user_prompt, agent="fullstack_agent", success=True
            )
        except ImportError:
            logger.warning("kb_operations_not_available")
        except Exception as kb_err:
            logger.exception("kb_update_failed", error=str(kb_err))

        # ======================================================================
        # STAGE 6: E2B SANDBOX DEPLOYMENT
        # ======================================================================
        await manager.send_progress_update(user_id, "sandbox_deployment", 85, "Deploying to sandbox...")

        preview_url = "/preview/placeholder"

        try:
            async with asyncio.timeout(60):
                sandbox_info = await e2b_manager.create_sandbox(project_id)

            async with asyncio.timeout(90):
                await e2b_manager.deploy_files(
                    project_id=project_id,
                    files=files,
                    websocket_manager=manager,
                    user_id=user_id
                )

            # Run npm install only if new packages were declared
            if needs_npm:
                await manager.send_progress_update(
                    user_id, "sandbox_deployment", 88,
                    f"Installing {len(merged.new_packages)} new packages..."
                )
                try:
                    async with asyncio.timeout(180):
                        await e2b_manager.install_dependencies(
                            project_id=project_id,
                            preview_mode="fullstack",
                            websocket_manager=manager,
                            user_id=user_id
                        )
                except asyncio.TimeoutError:
                    logger.warning("npm_install_timed_out", project_id=project_id)
            else:
                logger.info("skipping_npm_install_no_new_packages", project_id=project_id)

            async with asyncio.timeout(60):
                server_info = await e2b_manager.start_servers(
                    project_id=project_id,
                    preview_mode="fullstack",
                    websocket_manager=manager,
                    user_id=user_id
                )
                preview_url = server_info.get("preview_url", preview_url)

            # Persist sandbox session
            await db.sandbox_sessions.update_one(
                {"project_id": project_id},
                {"$set": {
                    "session_id": str(uuid.uuid4()),
                    "sandbox_id": sandbox_info.get("sandbox_id"),
                    "preview_url": preview_url,
                    "status": "active",
                    "last_active": datetime.utcnow(),
                    "server_command": "npm run dev",
                    "port": 3000,
                    "preview_mode": "fullstack",
                    "created_at": datetime.utcnow()
                }},
                upsert=True
            )

            await manager.send_message(user_id, {
                "type": "preview_ready",
                "payload": {"preview_url": preview_url, "project_id": project_id}
            })

        except asyncio.TimeoutError:
            logger.error("sandbox_timeout", project_id=project_id)
        except Exception as e:
            logger.error("sandbox_deployment_failed", project_id=project_id, error=str(e))

        # ======================================================================
        # STAGE 7: COMPLETION
        # ======================================================================
        await manager.send_progress_update(user_id, "complete", 100, "Code generation complete!")
        await manager.send_completion(
            user_id,
            project_id=project_id,
            preview_url=preview_url,
            scp_version="1.0",
            credits_used=credits_required
        )

        logger.info(
            "code_generation_completed",
            user_id=user_id, project_id=project_id,
            file_count=len(files), credits_used=credits_required,
            agent_calls=len(calls)
        )

    except Exception as e:
        logger.exception("code_generation_failed", user_id=user_id, project_id=project_id, error=str(e))
        await manager.send_error(user_id, "Code generation failed. Please try again.", "GENERATION_ERROR", retry_allowed=True)


# ============================================================================
# FOLLOW-UP MODIFICATION
# ============================================================================

async def handle_code_modification(user_id: str, data: dict):
    """
    Handle project modification (follow-up) using QAP modify operations.
    """
    payload = data.get("payload", {})
    user_prompt = payload.get("prompt")
    project_id = payload.get("project_id")

    if not user_prompt or not project_id:
        await manager.send_error(user_id, "Missing prompt or project_id", "INVALID_REQUEST")
        return

    logger.info("code_modification_started", user_id=user_id, project_id=project_id)

    db = await get_database()

    try:
        # Verify project ownership
        project = await db.projects.find_one({"project_id": project_id, "user_id": user_id})
        if not project:
            await manager.send_error(user_id, "Project not found", "PROJECT_NOT_FOUND")
            return

        # ======================================================================
        # STAGE 1: LOAD EXISTING FILES
        # ======================================================================
        await manager.send_progress_update(user_id, "orchestration", 15, "Loading project context...")

        existing_files: Dict[str, str] = {}
        async for blob in db.code_blobs.find({"file_id": {"$regex": f"^{project_id}:"}}):
            existing_files[blob["path"]] = blob["content"]

        # ======================================================================
        # STAGE 2: HUB ORCHESTRATION
        # ======================================================================
        await manager.send_progress_update(user_id, "orchestration", 25, "Analyzing modification...")

        result: CentralHubOutput = await get_central_hub().process_message(
            user_message=user_prompt,
            discussion_mode=False,
            project_id=project_id,
            user_id=user_id
        )

        intent = result.intent

        if intent not in ("follow_up", "code_generation"):
            await manager.send_message(user_id, {
                "type": "response",
                "payload": {"intent": intent, "response": result.response}
            })
            return

        scp = result.scp
        complexity = result.complexity or "moderate"
        credits_map = {"simple": 8, "moderate": 15, "complex": 25}
        credits_required = credits_map.get(complexity, 15)

        # ======================================================================
        # STAGE 3: CREDITS
        # ======================================================================
        credit_deducted = await deduct_credits(
            user_id, credits_required, f"Modification: {project.get('name')}", project_id
        )
        if not credit_deducted:
            await manager.send_error(
                user_id, f"Insufficient credits. Required: {credits_required}",
                "INSUFFICIENT_CREDITS", retry_allowed=False
            )
            return

        # ======================================================================
        # STAGE 4: AGENT EXECUTION (single-call modify)
        # ======================================================================
        await manager.send_progress_update(user_id, "code_generation", 50, "Generating modifications...")

        scp_dict = scp.model_dump() if hasattr(scp, "model_dump") else scp
        # Bug fix: pass ALL existing files so agent has full context for surgical modify ops.
        # Filtering to only affected_files was starving the agent — it got an empty dict
        # and fell back to rewriting everything from scratch.
        scp_dict["existing_files"] = existing_files

        try:
            agent_output: AgentOutputSchema = await get_fullstack_agent().execute(
                scp=scp_dict,
                task_type="follow_up",
                project_id=project_id,
                use_tools=True
            )
        except Exception as e:
            await rollback_credits(user_id, credits_required, "Agent execution failed")
            raise e

        # ======================================================================
        # STAGE 5: EXECUTE QAP OPERATIONS
        # ======================================================================
        updated_files = await _execute_operations(agent_output.file_operations, existing_files)
        modified_paths = [op.path for op in agent_output.file_operations if op.operation != "delete"]
        deleted_paths = [op.path for op in agent_output.file_operations if op.operation == "delete"]
        needs_npm = _check_npm_install_needed(agent_output.file_operations, agent_output.new_packages)

        # ======================================================================
        # STAGE 6: SANDBOX HOT RELOAD
        # ======================================================================
        await manager.send_progress_update(user_id, "sandbox_update", 75, "Applying changes to sandbox...")

        preview_url = None

        # Only deploy changed/new files for hot reload efficiency
        changed_files = {op.path: updated_files[op.path] for op in agent_output.file_operations
                        if op.operation in ("write", "modify") and op.path in updated_files}

        # Bug fix: replaced `project_id in e2b_manager.active_sandboxes` (in-memory only,
        # always empty after server restart) with get_active_sandbox() which handles:
        #   1) sandbox alive in memory → return it
        #   2) sandbox dead/missing → recreate from code_blobs in MongoDB
        #   3) no files found → return None → fall through to full create
        sandbox = await e2b_manager.get_active_sandbox(project_id)

        if sandbox is not None:
            # Hot reload — sandbox available (in-memory or freshly recreated from DB)
            await e2b_manager.deploy_files(project_id, changed_files, manager, user_id)

            # Delete removed files
            for del_path in deleted_paths:
                try:
                    await e2b_manager.delete_file(project_id, del_path)
                except Exception:
                    pass

            if needs_npm:
                try:
                    async with asyncio.timeout(180):
                        await e2b_manager.install_dependencies(project_id, "fullstack", manager, user_id)
                except asyncio.TimeoutError:
                    logger.warning("npm_install_timed_out_followup")

            preview_url = e2b_manager.get_preview_url(project_id)
        else:
            # No sandbox and no files in DB — create fresh (edge case: first-ever follow-up)
            await e2b_manager.create_sandbox(project_id)
            await e2b_manager.deploy_files(project_id, updated_files, manager, user_id)
            if needs_npm:
                await e2b_manager.install_dependencies(project_id, "fullstack", manager, user_id)
            server_result = await e2b_manager.start_servers(project_id, "fullstack", manager, user_id)
            preview_url = server_result.get("preview_url")

        # ======================================================================
        # STAGE 7: UPDATE DATABASE
        # ======================================================================
        for file_path, content in changed_files.items():
            await db.code_blobs.update_one(
                {"file_id": f"{project_id}:{file_path}"},
                {"$set": {"content": content, "updated_at": datetime.utcnow()}},
                upsert=True
            )

        for del_path in deleted_paths:
            await db.code_blobs.delete_one({"file_id": f"{project_id}:{del_path}"})

        # ======================================================================
        # COMPLETE
        # ======================================================================
        await manager.send_message(user_id, {
            "type": "generation_complete",
            "payload": {
                "project_id": project_id,
                "preview_url": preview_url,
                "files_modified": modified_paths,
                "files_deleted": deleted_paths,
                "scp_version": getattr(scp, "version", "1.1"),
                "hot_reload": project_id in e2b_manager.active_sandboxes
            }
        })

        logger.info(
            "code_modification_complete",
            project_id=project_id,
            files_modified=len(modified_paths),
            files_deleted=len(deleted_paths)
        )

    except Exception as e:
        logger.exception("code_modification_failed", user_id=user_id, project_id=project_id)
        await manager.send_error(user_id, "Modification failed", "MODIFICATION_ERROR", retry_allowed=True)
