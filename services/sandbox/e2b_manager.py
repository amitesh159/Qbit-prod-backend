"""
E2B Sandbox Manager - Production Grade (Refactored)
====================================================

Enterprise-ready E2B sandbox manager for Qbit fullstack applications.
Optimized for Next.js 16 + Express monorepo deployment with live preview.

Features:
- Monorepo structure support (frontend/ + backend/ + ai_services/)
- Package.json injection with verified versions
- Human-readable installation logs
- Health checks and auto-reconnection
- Hot reload support for follow-ups
- Graceful cleanup on inactivity
- Process management (frontend:3000, backend:8000, ai:7000)

Author: Qbit Engineering Team
Version: 2.0.0
"""

import json
import asyncio
import structlog
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from pathlib import Path
import os

logger = structlog.get_logger(__name__)

# ============================================================================
# CONFIGURATION & TEMPLATES
# ============================================================================

# Verified package.json templates (prevent LLM hallucinations)
FRONTEND_PACKAGE_JSON = {
    "name": "frontend",
    "version": "0.1.0",
    "private": True,
    "scripts": {
        "dev": "next dev -p 3000",
        "build": "next build",
        "start": "next start -p 3000",
        "lint": "next lint"
    },
    "dependencies": {
        "next": "16.1.6",
        "react": "19.0.0",
        "react-dom": "19.0.0",
        "class-variance-authority": "^0.7.1",
        "clsx": "^2.1.1",
        "tailwind-merge": "^2.5.5",
        "lucide-react": "^0.468.0"
    },
    "devDependencies": {
        "@tailwindcss/postcss": "^4.1.18",
        "@types/node": "^22.10.5",
        "@types/react": "^19.0.6",
        "@types/react-dom": "^19.0.3",
        "eslint": "^9.39.2",
        "eslint-config-next": "16.1.6",
        "tailwindcss": "^4.1.18",
        "typescript": "^5.9.3"
    }
}

BACKEND_PACKAGE_JSON = {
    "name": "backend",
    "version": "0.1.0",
    "private": True,
    "scripts": {
        "dev": "tsx watch src/server.ts",
        "build": "tsc",
        "start": "node dist/server.js"
    },
    "dependencies": {
        "express": "^4.21.2",
        "cors": "^2.8.5",
        "dotenv": "^16.4.7"
    },
    "devDependencies": {
        "@types/express": "^5.0.0",
        "@types/cors": "^2.8.17",
        "@types/node": "^22.10.5",
        "tsx": "^4.19.2",
        "typescript": "^5.9.3"
    }
}

AI_SERVICES_PACKAGE_JSON = {
    "name": "ai_services",
    "version": "0.1.0",
    "private": True,
    "scripts": {
        "dev": "tsx watch src/server.ts",
        "build": "tsc",
        "start": "node dist/server.js"
    },
    "dependencies": {
        "express": "^4.21.2",
        "cors": "^2.8.5",
        "dotenv": "^16.4.7"
    },
    "devDependencies": {
        "@types/express": "^5.0.0",
        "@types/cors": "^2.8.17",
        "@types/node": "^22.10.5",
        "tsx": "^4.19.2",
        "typescript": "^5.9.3"
    }
}


class SandboxProcess:
    """Represents a running process in the sandbox"""
    def __init__(self, pid: int, command: str, port: int, name: str):
        self.pid = pid
        self.command = command
        self.port = port
        self.name = name  # 'frontend' | 'backend' | 'ai_services'
        self.started_at = datetime.utcnow()
        self.is_healthy = True


class E2BManager:
    """
    Production-grade E2B Sandbox Manager for Qbit.
    
    Workflow:
    1. create_sandbox() - Initialize E2B Code Interpreter
    2. deploy_files() - Write all files using filesystem API
    3. inject_package_json() - Add verified package.json templates
    4. install_dependencies() - Run npm install with human-readable logs
    5. start_servers() - Launch frontend/backend/ai services
    6. get_preview_url() - Return live preview URL
    
    Auto-reconnection:
    - Health checks every 60s
    - Recreate dead sandboxes from MongoDB
    - Preserve user state across reconnections
    """
    
    def __init__(self, api_key: str, template_id: str, timeout: int = 3600, max_sandboxes: int = 10):
        """
        Initialize E2B Manager.
        
        Args:
            api_key: E2B API key
            template_id: E2B template ID (required)
            timeout: Sandbox timeout in seconds (default: 1 hour)
            max_sandboxes: Maximum number of concurrent sandboxes
        """
        if not api_key:
            raise ValueError("E2B API key is required")
        if not template_id:
            raise ValueError("E2B template_id is required")
        
        self.api_key = api_key
        self.template_id = template_id
        self.timeout = timeout
        self.max_sandboxes = max_sandboxes
        self.sandbox_ttl_minutes = 30  # Auto-cleanup after 30min inactivity
        
        # Storage
        self.active_sandboxes: Dict[str, Any] = {}  # project_id -> Sandbox
        self.sandbox_ids: Dict[str, str] = {}  # project_id -> sandbox_id
        self.sandbox_processes: Dict[str, List[SandboxProcess]] = {}  # project_id -> [processes]
        self.last_activity: Dict[str, datetime] = {}  # project_id -> timestamp
        self.sandbox_metadata: Dict[str, Dict] = {}  # project_id -> {preview_mode, ports, etc}
        
        logger.info("e2b_manager_initialized", timeout=timeout, max_sandboxes=max_sandboxes, template_id=template_id)
    
    def is_available(self) -> bool:
        """Check if E2B manager is properly initialized"""
        return self.api_key is not None and len(self.api_key) > 0
    
    # ========================================================================
    # SANDBOX LIFECYCLE
    # ========================================================================
    
    async def create_sandbox(self, project_id: str) -> Dict[str, Any]:
        """
        Create new E2B Code Interpreter sandbox.
        
        Returns:
            {
                "sandbox_id": str,
                "project_id": str,
                "status": "active"
            }
        """
        try:
            from e2b_code_interpreter import Sandbox
            
            logger.info("[E2B] Creating sandbox...", project_id=project_id)
            
            # Enforce sandbox limit
            await self._enforce_sandbox_limit()
            
            # Create sandbox (blocking operation - run in executor)
            loop = asyncio.get_event_loop()
            
            def _init_sandbox():
                # Use Sandbox.create() classmethod (NOT the deprecated constructor)
                # template and api_key are keyword arguments
                return Sandbox.create(
                    template=self.template_id,
                    timeout=self.timeout,
                    api_key=self.api_key,
                )

            sandbox = await loop.run_in_executor(
                None,
                _init_sandbox
            )
            
            # Extract sandbox ID
            sandbox_id = getattr(sandbox, 'sandbox_id', None) or getattr(sandbox, 'id', 'unknown')
            
            # Store sandbox
            self.active_sandboxes[project_id] = sandbox
            self.sandbox_ids[project_id] = sandbox_id
            self.last_activity[project_id] = datetime.utcnow()
            self.sandbox_processes[project_id] = []
            self.sandbox_metadata[project_id] = {}
            
            logger.info("[E2B] ✅ Sandbox created", project_id=project_id, sandbox_id=sandbox_id)
            
            return {
                "sandbox_id": sandbox_id,
                "project_id": project_id,
                "status": "active"
            }
            
        except Exception as e:
            logger.exception("[E2B] ❌ Sandbox creation failed", project_id=project_id, error=str(e))
            raise
    
    async def deploy_files(
        self,
        project_id: str,
        files: Dict[str, str],
        websocket_manager: Any = None,
        user_id: Optional[str] = None,
        preview_mode: str = "fullstack"
    ) -> bool:
        """
        Deploy files to sandbox using parallel batch upload.
        
        Files are uploaded in batches of 10 formax performance.
        Based on E2B best practices for fast deployments.
        
        Args:
            project_id: Unique project identifier
            files: Dict of {path: content}
            websocket_manager: Optional websocket for progress updates
            user_id: Optional user ID for websocket
            preview_mode: "fullstack" | "frontend_only" | "backend_only"
        
        Returns:
            True if successful
        """
        if project_id not in self.active_sandboxes:
            logger.error("[E2B] Sandbox not found", project_id=project_id)
            return False
        
        sandbox = self.active_sandboxes[project_id]
        
        try:
            logger.info("[E2B] Deploying files...", project_id=project_id, file_count=len(files))
            
            if websocket_manager and user_id:
                await websocket_manager.send_sandbox_status(
                    user_id=user_id,
                    stage="deploying",
                    message_text=f"📦 Uploading {len(files)} files to sandbox...",
                    sandbox_id=self.sandbox_ids.get(project_id),
                    progress=10
                )
            
            # Store metadata
            self.sandbox_metadata[project_id] = {"preview_mode": preview_mode}
            
            # Split files into batches of 10 for parallel upload
            file_items = list(files.items())
            batch_size = 10
            batches = [file_items[i:i+batch_size] for i in range(0, len(file_items), batch_size)]
            
            total_files = len(files)
            uploaded_count = 0
            
            loop = asyncio.get_event_loop()
            
            # Process each batch in parallel
            for batch_num, batch in enumerate(batches, 1):
                # Upload batch in parallel
                upload_tasks = []
                for path, content in batch:
                    # Normalize path (remove leading slash if present)
                    normalized_path = path.lstrip('/')
                    
                    # Create upload task
                    task = loop.run_in_executor(
                        None,
                        lambda p=normalized_path, c=content: sandbox.files.write(p, c)
                    )
                    upload_tasks.append((path, task))
                
                # Wait for all files in this batch to complete
                for path, task in upload_tasks:
                    try:
                        await task
                        uploaded_count += 1
                    except Exception as e:
                        logger.error(f"[E2B] Failed to upload {path}: {str(e)}")
                        raise
                
                # Progress update after each batch
                if websocket_manager and user_id:
                    progress = 10 + int((uploaded_count / total_files) * 10)  # 10-20%
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="deploying",
                        message_text=f"📦 Uploaded {uploaded_count}/{total_files} files...",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=progress
                    )
            
            logger.info("[E2B] ✅ Files deployed successfully", project_id=project_id)
            return True
            
        except Exception as e:
            logger.exception("[E2B] ❌ File deployment failed", project_id=project_id, error=str(e))
            return False
    
    async def inject_package_json(
        self,
        project_id: str,
        files: Dict[str, str],
        additional_dependencies: Optional[Dict] = None,
        websocket_manager: Any = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Inject verified package.json files with best-practice configs.
        
        TEMPLATE MODE: Returns success immediately since package.json files
        are pre-installed in the E2B template.
        
        Args:
            project_id: Project ID
            files: Dict of file paths to content (for checking what exists)
            additional_dependencies: Optional extra dependencies to merge
            websocket_manager: Optional WebSocket manager for progress
            user_id: Optional user ID for WebSocket
            
        Returns:
            True (always, since template has package.json)
        """
        logger.info(
            "[E2B] Template mode: Skipping inject_package_json (pre-installed)",
            project_id=project_id,
            template_id=self.template_id
        )
        return True
    
    async def install_dependencies(
        self,
        project_id: str,
        preview_mode: str = "fullstack",
        websocket_manager: Any = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Install npm dependencies for frontend, backend, and AI services.
        
        TEMPLATE MODE: Returns success immediately since all dependencies
        (Next.js, React, shadcn/ui, etc.) are pre-installed in the template.
        
        Args:
            project_id: Project ID
            preview_mode: "frontend", "fullstack", "backend"
            websocket_manager: Optional WebSocket manager for progress
            user_id: Optional user ID for WebSocket
            
        Returns:
            Dict with success status (always True in template mode)
        """
        logger.info(
            "[E2B] Template mode: Skipping install_dependencies (pre-installed)",
            project_id=project_id,
            template_id=self.template_id,
            preview_mode=preview_mode
        )
        return {
            "success": True,
            "frontend_installed": True,
            "backend_installed": True,
            "ai_installed": True, # Changed from ai_services_installed to ai_installed
            "message": "Dependencies pre-installed in template"
        }
        """
        Install npm dependencies with clean, minimal logging.
        
        Based on E2B expert patterns:
        - Only install for directories that exist (conditional)
        - Use --silent flag to reduce output spam
        - Sequential installation (avoid npm lock conflicts)
        - Minimal logging (start, end, summary only)
        
        Returns:
            {
                "success": bool,
                "frontend_installed": bool,
                "backend_installed": bool,
                "ai_installed": bool,
                "error": Optional[str]
            }
        """
        if project_id not in self.active_sandboxes:
            return {"success": False, "error": "Sandbox not found"}
        
        sandbox = self.active_sandboxes[project_id]
        loop = asyncio.get_event_loop()
        
        result = {
            "success": False,
            "frontend_installed": False,
            "backend_installed": False,
            "ai_installed": False,
            "error": None
        }
        
        try:
            # Check which directories exist (CONDITIONAL INSTALLATION)
            has_frontend = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("frontend/package.json")
            )
            has_backend = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("backend/package.json")
            )
            has_ai = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("ai_services/package.json")
            )
            
            logger.info(
                f"[E2B] Installing dependencies (frontend={has_frontend}, backend={has_backend}, ai={has_ai})"
            )
            
            if websocket_manager and user_id:
                await websocket_manager.send_sandbox_status(
                    user_id=user_id,
                    stage="installing",
                    message_text="📦 Installing npm packages...",
                    sandbox_id=self.sandbox_ids.get(project_id),
                    progress=30
                )
            
            # FRONTEND INSTALLATION (if exists)
            if has_frontend:
                logger.info("[E2B] Installing frontend dependencies...")
                
                if websocket_manager and user_id:
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="installing",
                        message_text="⚛️ Installing React & Next.js...",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=40
                    )
                
                cmd_result = await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm install --legacy-peer-deps --silent",  # --silent reduces spam
                        cwd="frontend",
                        timeout=300
                    )
                )
                
                if cmd_result.exit_code == 0:
                    # Parse summary from output
                    if "added" in cmd_result.stdout:
                        summary = [line for line in cmd_result.stdout.split('\n') if 'added' in line]
                        if summary:
                            logger.info(f"[E2B] ✅ Frontend: {summary[0].strip()}")
                    else:
                        logger.info("[E2B] ✅ Frontend dependencies installed")
                    result["frontend_installed"] = True
                    
                    # Install shadcn/ui components after successful npm install
                    await self._install_shadcn_components(
                        sandbox, loop, project_id, websocket_manager, user_id
                    )
                else:
                    logger.error(f"[E2B] ❌ Frontend install failed: {cmd_result.stderr[:200]}")
                    result["error"] = "Frontend dependency installation failed"
                    return result  # Frontend is critical, abort if it fails
            
            # BACKEND INSTALLATION (if exists)
            if has_backend:
                logger.info("[E2B] Installing backend dependencies...")
                
                if websocket_manager and user_id:
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="installing",
                        message_text="🔧 Installing Express & TypeScript...",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=60
                    )
                
                cmd_result = await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm install --legacy-peer-deps --silent",
                        cwd="backend",
                        timeout=300
                    )
                )
                
                if cmd_result.exit_code == 0:
                    logger.info("[E2B] ✅ Backend dependencies installed")
                    result["backend_installed"] = True
                else:
                    logger.error(f"[E2B] ❌ Backend install failed")
                    # Don't abort - backend is optional
            
            # AI SERVICES INSTALLATION (if exists)
            if has_ai:
                logger.info("[E2B] Installing AI service dependencies...")
                
                if websocket_manager and user_id:
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="installing",
                        message_text="🤖 Installing AI service dependencies...",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=70
                    )
                
                cmd_result = await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm install --legacy-peer-deps --silent",
                        cwd="ai_services",
                        timeout=300
                    )
                )
                
                if cmd_result.exit_code == 0:
                    logger.info("[E2B] ✅ AI services dependencies installed")
                    result["ai_installed"] = True
                else:
                    logger.warning("[E2B] ⚠️ AI services install failed (non-critical)")
            
            # Overall success if at least frontend installed
            result["success"] = result["frontend_installed"]
            
            if result["success"]:
                logger.info("[E2B] ✅ Dependencies installed successfully")
            
            return result
            
        except Exception as e:
            logger.exception("[E2B] ❌ Dependency installation failed", error=str(e))
            return {
                "success": False,
                "frontend_installed": False,
                "backend_installed": False,
                "ai_installed": False,
                "error": str(e)
            }
    
    async def start_servers(
        self,
        project_id: str,
        preview_mode: str = "fullstack",
        websocket_manager: Any = None,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Start development servers using E2B expert pattern (compile.sh).
        
        Pattern:
        - Background processes with & operator
        - Clean curl health checks
        - Minimal logging (only every 20 checks)
        
        Returns:
            {
                "success": bool,
                "preview_url": str,
                "frontend_ready": bool,
                "backend_ready": bool,
                "ai_ready": bool
            }
        """
        if project_id not in self.active_sandboxes:
            return {"success": False, "error": "Sandbox not found"}
        
        sandbox = self.active_sandboxes[project_id]
        loop = asyncio.get_event_loop()
        
        try:
            logger.info("[E2B] Starting development servers...", preview_mode=preview_mode)
            
            if websocket_manager and user_id:
                await websocket_manager.send_sandbox_status(
                    user_id=user_id,
                    stage="starting",
                    message_text="🚀 Starting development servers...",
                    sandbox_id=self.sandbox_ids.get(project_id),
                    progress=80
                )
            
            # Check which servers to start (CONDITIONAL)
            has_frontend = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("frontend")
            )
            has_backend = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("backend")
            )
            has_ai = await loop.run_in_executor(
                None, lambda: sandbox.files.exists("ai_services")
            )
            
            # START BACKEND (if exists)
            if has_backend:
                logger.info("[E2B] Starting backend server (port 8000)...")
                await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm run dev > /tmp/backend.log 2>&1 &",  # Background with &
                        cwd="backend",
                        timeout=5
                    )
                )
            
            # START AI SERVICES (if exists)
            if has_ai:
                logger.info("[E2B] Starting AI services server (port 7000)...")
                await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm run dev > /tmp/ai.log 2>&1 &",
                        cwd="ai_services",
                        timeout=5
                    )
                )
            
            # START FRONTEND (if exists)
            if has_frontend:
                logger.info("[E2B] Starting frontend server (port 3000)...")
                
                if websocket_manager and user_id:
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="starting",
                        message_text="⚛️ Starting Next.js...",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=90
                    )
                
                await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        "npm run dev > /tmp/frontend.log 2>&1 &",
                        cwd="frontend",
                        timeout=5
                    )
                )
                
                # WAIT FOR FRONTEND USING COMPILE.SH CLEAN PATTERN
                logger.info("[E2B] Waiting for Next.js to compile...")
                frontend_ready = await self._wait_for_server_clean(sandbox, port=3000, timeout=240)
                
                if not frontend_ready:
                    logger.error("[E2B] ❌ Frontend server failed to start")
                    return {
                        "success": False,
                        "error": "Frontend server timeout"
                    }
                
                logger.info("[E2B] ✅ Frontend server ready")
            
            # Get preview URL
            preview_url = None
            if has_frontend:
                try:
                    host = sandbox.get_host(3000)
                    preview_url = f"https://{host}"
                except Exception as e:
                    logger.error(f"[E2B] Failed to get preview URL: {e}")
            
            logger.info("[E2B] ✅ All servers started successfully")
            
            return {
                "success": True,
                "preview_url": preview_url,
                "frontend_ready": has_frontend,
                "backend_ready": has_backend,
                "ai_ready": has_ai
            }
            
        except Exception as e:
            logger.exception("[E2B] ❌ Server startup failed", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _install_shadcn_components(
        self,
        sandbox: Any,
        loop: Any,
        project_id: str,
        websocket_manager: Any = None,
        user_id: Optional[str] = None
    ) -> bool:
        """
        Install shadcn/ui components in the frontend.
        
        TEMPLATE MODE: Returns success immediately since 50+ shadcn/ui
        components are pre-installed in the template.
        
        Args:
            sandbox: E2B sandbox instance
            loop: Event loop
            project_id: Project ID
            websocket_manager: Optional WebSocket manager
            user_id: Optional user ID
            
        Returns:
            True (always, since template has shadcn/ui)
        """
        logger.info(
            "[E2B] Template mode: Skipping shadcn install (pre-installed)",
            project_id=project_id,
            template_id=self.template_id
        )
        return True
        """
        Install shadcn/ui components in frontend directory.
        
        This runs after npm install and creates /frontend/components/ui/*
        with all shadcn components (Button, Card, Input, etc.).
        
        Non-blocking: Logs warning if fails but doesn't abort deployment.
        
        Args:
            sandbox: E2B sandbox instance
            loop: Asyncio event loop
            project_id: Project identifier
            websocket_manager: Optional websocket for progress updates
            user_id: Optional user ID for websocket
            
        Returns:
            True if successful, False if failed (non-critical)
        """
        try:
            logger.info("[E2B] Installing shadcn/ui components...")
            
            if websocket_manager and user_id:
                await websocket_manager.send_sandbox_status(
                    user_id=user_id,
                    stage="installing",
                    message_text="Installing UI components...",
                    sandbox_id=self.sandbox_ids.get(project_id),
                    progress=50
                )
            
            # Initialize shadcn (creates components.json + lib/utils.ts)
            init_result = await loop.run_in_executor(
                None,
                lambda: sandbox.commands.run(
                    "npx shadcn@latest init -d --yes",
                    cwd="frontend",
                    timeout=120
                )
            )
            
            if init_result.exit_code != 0:
                logger.warning(
                    "[E2B] shadcn init failed (non-critical)",
                    stderr=init_result.stderr[:200]
                )
                return False
            
            logger.info("[E2B] shadcn initialized")
            
            # Install all components
            add_result = await loop.run_in_executor(
                None,
                lambda: sandbox.commands.run(
                    "npx shadcn@latest add --all --yes",
                    cwd="frontend",
                    timeout=180
                )
            )
            
            if add_result.exit_code == 0:
                logger.info("[E2B] ✅ shadcn components installed")
                
                if websocket_manager and user_id:
                    await websocket_manager.send_sandbox_status(
                        user_id=user_id,
                        stage="installing",
                        message_text="UI components ready",
                        sandbox_id=self.sandbox_ids.get(project_id),
                        progress=55
                    )
                return True
            else:
                logger.warning(
                    "[E2B] shadcn add failed (non-critical)",
                    stderr=add_result.stderr[:200]
                )
                return False
                
        except Exception as e:
            logger.warning(
                "[E2B] shadcn installation failed (non-critical)",
                error=str(e)
            )
            return False
    
    async def _wait_for_server_clean(
        self,
        sandbox: Any,
        port: int,
        timeout: int = 180
    ) -> bool:
        """
        Clean health check pattern inspired by E2B compile.sh ping_server function.
        
        Polls server with curl until HTTP 200, minimal logging.
        Only logs every 20 checks to avoid spam (E2B expert pattern).
        
        Args:
            sandbox: E2B sandbox instance
            port: Port to check
            timeout: Maximum wait time in seconds
        
        Returns:
            Truef server is ready, False if timeout
        """
        loop = asyncio.get_event_loop()
        start_time = datetime.utcnow()
        counter = 0
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            counter += 1
            
            # Only log every 20 checks 
            if counter % 20 == 0:
                elapsed = int((datetime.utcnow() - start_time).total_seconds())
                logger.info(f"[E2B] Still waiting for server on port {port}... ({elapsed}s)")
            
            try:
                # Clean curl pattern from compile.sh
                result = await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        f'curl -s -o /dev/null -w "%{{http_code}}" http://localhost:{port}',
                        timeout=5
                    )
                )
                
                # Check HTTP status code
                if result.exit_code == 0:
                    http_code = result.stdout.strip()
                    # Accept any valid HTTP response (2xx, 3xx, 4xx are all signs server is running)
                    # Next.js dev server might return 404 before routes are ready
                    if http_code and http_code.isdigit() and int(http_code) >= 200 and int(http_code) < 600:
                        logger.info(f"[E2B] ✅ Server ready on port {port} (HTTP {http_code})")
                        return True
                    elif counter % 10 == 0:  # Log unexpected codes occasionally
                        logger.debug(f"[E2B] Unexpected HTTP code: {http_code}")
            
            except Exception:
                pass  # Silent failure, just retry
            
            await asyncio.sleep(0.5)  # Check every 0.5s (faster than compile.sh)
        
        logger.error(f"[E2B] ❌ Server timeout on port {port} after {timeout}s")
        return False
    
    async def _wait_for_server(
        self,
        sandbox: Any,
        port: int,
        timeout: int = 180
    ) -> bool:
        """
        Wait for server to be ready using health checks.
        
        Args:
            sandbox: E2B sandbox instance
            port: Port to check
            timeout: Maximum wait time in seconds
        
        Returns:
            True if server is ready, False if timeout
        """
        logger.info(f"[E2B] Waiting for server on port {port} (timeout: {timeout}s)")
        
        loop = asyncio.get_event_loop()
        start_time = datetime.utcnow()
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            try:
                # Try to connect to the server
                result = await loop.run_in_executor(
                    None,
                    lambda: sandbox.commands.run(
                        f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:{port}",
                        timeout=5
                    )
                )
                
                # Check if we got a valid HTTP response
                if result.exit_code == 0 and result.stdout.strip() in ['200', '404', '301', '302']:
                    logger.info(f"[E2B] ✅ Server ready on port {port}")
                    return True
                
            except Exception as e:
                logger.debug(f"[E2B] Server not ready yet on port {port}", error=str(e))
            
            await asyncio.sleep(3)  # Check every 3 seconds
        
        logger.warning(f"[E2B] ⚠️ Timeout waiting for server on port {port}")
        return False
    
    # ========================================================================
    # SANDBOX MANAGEMENT
    # ========================================================================
    
    async def get_active_sandbox(self, project_id: str) -> Optional[Any]:
        """
        Get active sandbox with auto-reconnection.
        
        If sandbox is dead, recreates from MongoDB.
        """
        try:
            # Check if exists locally
            if project_id not in self.active_sandboxes:
                logger.info("[E2B] Sandbox not found, attempting recreation", project_id=project_id)
                return await self._recreate_sandbox_from_db(project_id)
            
            sandbox = self.active_sandboxes[project_id]
            
            # Health check
            is_healthy = await self._check_sandbox_health(sandbox)
            
            if not is_healthy:
                logger.warning("[E2B] Sandbox unhealthy, recreating", project_id=project_id)
                await self.cleanup_sandbox(project_id)
                return await self._recreate_sandbox_from_db(project_id)
            
            # Update activity
            self.last_activity[project_id] = datetime.utcnow()
            return sandbox
            
        except Exception as e:
            logger.exception("[E2B] Failed to get active sandbox", project_id=project_id, error=str(e))
            return None
    
    async def _check_sandbox_health(self, sandbox: Any) -> bool:
        """Simple health check"""
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: sandbox.commands.run("echo health_check", timeout=5)
            )
            return result.exit_code == 0
        except:
            return False
    
    async def _recreate_sandbox_from_db(self, project_id: str) -> Optional[Any]:
        """
        Recreate sandbox from MongoDB stored files.
        
        Per PRD: "Support live preview reconnection"
        """
        try:
            logger.info("[E2B] Recreating sandbox from database", project_id=project_id)
            
            # Import here to avoid circular dependency
            from database.connection import get_database
            db = await get_database()
            
            # Fetch files from MongoDB
            files = {}
            async for blob in db.code_files.find({"file_id": {"$regex": f"^{project_id}:"}}):
                files[blob["path"]] = blob["content"]
            
            if not files:
                logger.warning("[E2B] No files found in database", project_id=project_id)
                return None
            
            # Get preview mode
            session = await db.sandbox_sessions.find_one({"project_id": project_id})
            preview_mode = session.get("preview_mode", "fullstack") if session else "fullstack"
            
            logger.info("[E2B] Recreating sandbox", 
                       project_id=project_id,
                       file_count=len(files),
                       preview_mode=preview_mode)
            
            # Create new sandbox
            await self.create_sandbox(project_id)
            
            # Deploy files
            await self.deploy_files(project_id, files, preview_mode=preview_mode)
            
            # Inject package.json
            await self.inject_package_json(project_id, files)
            
            # Install dependencies
            install_result = await self.install_dependencies(project_id, preview_mode)
            
            if not install_result["success"]:
                logger.error("[E2B] Recreation failed: dependency install error", project_id=project_id)
                return None
            
            # Start servers
            server_result = await self.start_servers(project_id, preview_mode)
            
            if not server_result["success"]:
                logger.error("[E2B] Recreation failed: server startup error", project_id=project_id)
                return None
            
            logger.info("[E2B] ✅ Sandbox recreated successfully",
                       project_id=project_id,
                       preview_url=server_result.get("preview_url"))
            
            return self.active_sandboxes.get(project_id)
            
        except Exception as e:
            logger.exception("[E2B] Sandbox recreation failed", project_id=project_id, error=str(e))
            return None
    
    async def cleanup_sandbox(self, project_id: str):
        """Clean up sandbox resources"""
        if project_id in self.active_sandboxes:
            try:
                sandbox = self.active_sandboxes[project_id]
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, sandbox.kill)
                
                self.active_sandboxes.pop(project_id, None)
                self.sandbox_ids.pop(project_id, None)
                self.sandbox_processes.pop(project_id, None)
                self.last_activity.pop(project_id, None)
                self.sandbox_metadata.pop(project_id, None)
                
                logger.info("[E2B] ✅ Sandbox cleaned up", project_id=project_id)
            except Exception as e:
                logger.error("[E2B] Cleanup error", project_id=project_id, error=str(e))
    
    async def cleanup_inactive_sandboxes(self):
        """Background task: cleanup inactive sandboxes"""
        current_time = datetime.utcnow()
        ttl_threshold = current_time - timedelta(minutes=self.sandbox_ttl_minutes)
        
        inactive_projects = [
            pid for pid, last_access in self.last_activity.items()
            if last_access < ttl_threshold
        ]
        
        for pid in inactive_projects:
            logger.info("[E2B] Cleaning up inactive sandbox", project_id=pid)
            await self.cleanup_sandbox(pid)
    
    async def _enforce_sandbox_limit(self):
        """Enforce maximum sandbox limit (LRU eviction)"""
        if len(self.active_sandboxes) >= self.max_sandboxes:
            lru_id = min(self.last_activity, key=self.last_activity.get)
            logger.warning("[E2B] Sandbox limit reached, evicting LRU", project_id=lru_id)
            await self.cleanup_sandbox(lru_id)
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    def get_preview_url(self, project_id: str) -> Optional[str]:
        """Get frontend preview URL"""
        sandbox = self.active_sandboxes.get(project_id)
        if not sandbox:
            return None
        
        try:
            host = sandbox.get_host(3000)
            return f"https://{host}"
        except Exception as e:
            logger.error("[E2B] Failed to get preview URL", project_id=project_id, error=str(e))
            return None
    
    def get_sandbox_info(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get sandbox information"""
        if project_id not in self.active_sandboxes:
            return None
        
        processes = self.sandbox_processes.get(project_id, [])
        
        return {
            "sandbox_id": self.sandbox_ids.get(project_id),
            "project_id": project_id,
            "status": "active",
            "metadata": self.sandbox_metadata.get(project_id, {}),
            "processes": [
                {
                    "name": p.name,
                    "port": p.port,
                    "pid": p.pid,
                    "command": p.command,
                    "started_at": p.started_at.isoformat()
                }
                for p in processes
            ]
        }
    
    async def update_files_hot_reload(
        self,
        project_id: str,
        updated_files: Dict[str, str]
    ) -> bool:
        """
        Hot reload: update files without restarting servers.
        
        Optimizations:
        - Compare diffs and skip unchanged files
        - Batch upload changed files in parallel
        - Next.js dev mode auto-reloads on file changes
        """
        if project_id not in self.active_sandboxes:
            return False
        
        sandbox = self.active_sandboxes[project_id]
        
        try:
            logger.info("[E2B] Hot reloading files...", 
                       project_id=project_id,
                       file_count=len(updated_files))
            
            loop = asyncio.get_event_loop()
            
            # Get existing files and compare diffs
            existing_files = {}
            for path in updated_files.keys():
                try:
                    normalized_path = path.lstrip('/')
                    content = await loop.run_in_executor(
                        None, lambda p=normalized_path: sandbox.files.read(p)
                    )
                    existing_files[path] = content
                except:
                    existing_files[path] = ""  # File doesn't exist yet
            
            # Filter out unchanged files (diff comparison)
            changed_files = {
                path: content
                for path, content in updated_files.items()
                if existing_files.get(path) != content
            }
            
            if not changed_files:
                logger.info("[E2B] No files changed, skipping hot reload")
                return True
            
            logger.info(f"[E2B] Hot reloading {len(changed_files)}/{len(updated_files)}changed files")
            
            # Upload changed files in parallel (batches of 10)
            file_items = list(changed_files.items())
            batch_size = 10
            batches = [file_items[i:i+batch_size] for i in range(0, len(file_items), batch_size)]
            
            for batch in batches:
                upload_tasks = []
                for path, content in batch:
                    normalized_path = path.lstrip('/')
                    task = loop.run_in_executor(
                        None,
                        lambda p=normalized_path, c=content: sandbox.files.write(p, c)
                    )
                    upload_tasks.append(task)
                
                # Wait for all files in this batch
                await asyncio.gather(*upload_tasks)
            
            logger.info("[E2B] ✅ Hot reload complete - Next.js will auto-refresh")
            return True
            
        except Exception as e:
            logger.exception("[E2B] Hot reload failed", error=str(e))
            return False


# ============================================================================
# SINGLETON INITIALIZATION (AUTO-LOADS FROM SETTINGS)
# ============================================================================

_e2b_manager_instance: Optional[E2BManager] = None


def _initialize_e2b_manager() -> E2BManager:
    """
    Initialize E2B manager from settings.
    
    This function is called automatically when the module is imported.
    """
    try:
        from config.settings import settings
        
        if not settings.e2b_api_key:
            logger.warning("[E2B] No API key found in settings - E2B features disabled")
            return None
        
        timeout = min(settings.e2b_timeout or 3600, 3600)
        max_sandboxes = settings.e2b_max_sandboxes or 10
        template_id = settings.e2b_template_id
        
        manager = E2BManager(
            api_key=settings.e2b_api_key,
            template_id=template_id,
            timeout=timeout,
            max_sandboxes=max_sandboxes
        )
        
        logger.info("[E2B] Manager initialized successfully",
                   timeout=timeout,
                   max_sandboxes=max_sandboxes,
                   template_id=template_id)
        
        return manager
        
    except ImportError as e:
        logger.error("[E2B] Failed to import settings", error=str(e))
        return None
    except Exception as e:
        logger.error("[E2B] Failed to initialize E2B manager", error=str(e))
        return None


def get_e2b_manager() -> E2BManager:
    """
    Get the E2B manager singleton instance.
    
    Returns:
        E2BManager instance or None if not initialized
    
    Raises:
        RuntimeError: If E2B manager is not available
    """
    global _e2b_manager_instance
    
    if _e2b_manager_instance is None:
        _e2b_manager_instance = _initialize_e2b_manager()
    
    if _e2b_manager_instance is None:
        raise RuntimeError(
            "E2B Manager is not available. Please check:\n"
            "1. E2B_API_KEY is set in environment variables\n"
            "2. config.settings module is accessible\n"
            "3. E2B SDK is installed: pip install e2b-code-interpreter"
        )
    
    return _e2b_manager_instance


# Auto-initialize on module import for backward compatibility
try:
    _e2b_manager_instance = _initialize_e2b_manager()
    # Export as 'e2b_manager' for backward compatibility
    e2b_manager = _e2b_manager_instance
except Exception as e:
    logger.warning(f"[E2B] Could not auto-initialize: {e}")
    e2b_manager = None