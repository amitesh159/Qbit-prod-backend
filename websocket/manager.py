"""
WebSocket Connection Manager
Manages real-time connections for chat and code generation progress
"""
import json
import uuid
import structlog
from typing import Dict, List, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
from datetime import datetime
from websocket.schemas import WSMessageFactory

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    WebSocket connection manager for real-time communication.
    Handles multiple concurrent user connections.
    """
    
    def __init__(self):
        # user_id -> WebSocket mapping
        self.active_connections: Dict[str, WebSocket] = {}
        # connection_id -> user_id mapping for tracking
        self.connection_ids: Dict[str, str] = {}
    
    async def connect(self, websocket: WebSocket, user_id: str) -> str:
        """
        Accept WebSocket connection and register user.
        
        Args:
            websocket: WebSocket connection
            user_id: User identifier
            
        Returns:
            str: Connection ID for tracking
        """
        await websocket.accept()
        
        connection_id = str(uuid.uuid4())
        self.active_connections[user_id] = websocket
        self.connection_ids[connection_id] = user_id
        
        logger.info(
            "websocket_connected",
            user_id=user_id,
            connection_id=connection_id,
            total_connections=len(self.active_connections)
        )
        
        # Send welcome message
        await self.send_message(user_id, {
            "type": "connected",
            "payload": {
                "connection_id": connection_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
        
        return connection_id
    
    def disconnect(self, user_id: str) -> None:
        """
        Disconnect user and cleanup connection.
        
        Args:
            user_id: User identifier
        """
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            
            # Remove from connection_ids
            connection_id_to_remove = None
            for conn_id, uid in self.connection_ids.items():
                if uid == user_id:
                    connection_id_to_remove = conn_id
                    break
            
            if connection_id_to_remove:
                del self.connection_ids[connection_id_to_remove]
            
            logger.info(
                "websocket_disconnected",
                user_id=user_id,
                remaining_connections=len(self.active_connections)
            )
    
    async def send_message(self, user_id: str, message: dict) -> bool:
        """
        Send JSON message to specific user.
        
        Args:
            user_id: Target user ID
            message: Message dict to send
            
        Returns:
            bool: True if sent successfully, False if user not connected
        """
        if user_id not in self.active_connections:
            logger.warning(
                "send_message_user_not_connected",
                user_id=user_id
            )
            return False
        
        try:
            await self.active_connections[user_id].send_json(message)
            
            logger.debug(
                "websocket_message_sent",
                user_id=user_id,
                message_type=message.get("type")
            )
            
            return True
            
        except Exception as e:
            logger.error(
                "websocket_send_failed",
                user_id=user_id,
                error=str(e)
            )
            # Disconnect on error
            self.disconnect(user_id)
            return False
    
    async def broadcast_message(self, message: dict) -> None:
        """
        Broadcast message to all connected users.
        
        Args:
            message: Message dict to broadcast
        """
        disconnected_users = []
        
        for user_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(
                    "broadcast_send_failed",
                    user_id=user_id,
                    error=str(e)
                )
                disconnected_users.append(user_id)
        
        # Cleanup disconnected users
        for user_id in disconnected_users:
            self.disconnect(user_id)
        
        logger.info(
            "websocket_broadcast_sent",
            message_type=message.get("type"),
            recipient_count=len(self.active_connections)
        )
    
    async def send_progress_update(
        self,
        user_id: str,
        stage: str,
        progress: int,
        message: str
    ) -> bool:
        """
        Send code generation progress update to user.
        
        Args:
            user_id: Target user ID
            stage: Current stage (scp_generation, agent_execution, sandbox_deployment)
            progress: Progress percentage (0-100)
            message: Human-readable status message
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "code_generation_progress",
            "payload": {
                "stage": stage,
                "progress": progress,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_completion(
        self,
        user_id: str,
        project_id: str,
        preview_url: str,
        scp_version: str,
        credits_used: int
    ) -> bool:
        """
        Send code generation completion notification.
        
        Args:
            user_id: Target user ID
            project_id: Generated project ID
            preview_url: Sandbox preview URL
            scp_version: SCP version used
            credits_used: Credits deducted
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "code_generation_complete",
            "payload": {
                "project_id": project_id,
                "preview_url": preview_url,
                "scp_version": scp_version,
                "credits_used": credits_used,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_error(
        self,
        user_id: str,
        error_message: str,
        error_code: str,
        retry_allowed: bool = False
    ) -> bool:
        """
        Send error notification to user.
        
        Args:
            user_id: Target user ID
            error_message: Error description
            error_code: Error code identifier
            retry_allowed: Whether retry is possible
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "error",
            "payload": {
                "message": error_message,
                "code": error_code,
                "retry_allowed": retry_allowed,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_prompt_received(
        self,
        user_id: str,
        prompt: str,
        discussion_mode: bool = False
    ) -> bool:
        """
        Send prompt_received notification.
        
        Args:
            user_id: Target user ID
            prompt: User's input prompt
            discussion_mode: Whether in discussion mode
            
        Returns:
            bool: True if sent successfully
        """
        message = WSMessageFactory.prompt_received(prompt, discussion_mode)
        message = WSMessageFactory.prompt_received(prompt, discussion_mode)
        return await self.send_message(user_id, message)
    
    async def send_project_created(
        self,
        user_id: str,
        project_id: str
    ) -> bool:
        """
        Send project_created notification immediately.
        
        Args:
            user_id: User identifier
            project_id: Project identifier
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "project_created",
            "payload": {
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_scp_generated(
        self,
        user_id: str,
        scp: Dict[str, Any],
        summary: str,
        complexity: str,
        credits_required: int,
        file_count: int = 0
    ) -> bool:
        """
        Send SCP generation complete notification.
        
        Args:
            user_id: Target user ID
            scp: Full SCP document
            summary: Human-readable summary
            complexity: simple, moderate, or complex
            credits_required: Credits needed
            file_count: Number of files
            
        Returns:
            bool: True if sent successfully
        """
        message = WSMessageFactory.scp_generated(
            scp=scp,
            summary=summary,
            complexity=complexity,
            credits_required=credits_required,
            file_count=file_count
        )
        return await self.send_message(user_id, message)
    
    async def send_agent_task_update(
        self,
        user_id: str,
        tasks: List[Dict[str, Any]],
        current_task_id: Optional[str] = None
    ) -> bool:
        """
        Send agent task progress update.
        
        Args:
            user_id: Target user ID
            tasks: List of task dictionaries
            current_task_id: ID of currently executing task
            
        Returns:
            bool: True if sent successfully
        """
        message = WSMessageFactory.agent_task_update(tasks, current_task_id)
        return await self.send_message(user_id, message)
    
    async def send_code_token(
        self,
        user_id: str,
        token: str,
        file_path: Optional[str] = None,
        language: Optional[str] = None
    ) -> bool:
        """
        Send streaming code token to client for real-time preview.
        
        Args:
            user_id: User identifier
            token: Code token to send
            file_path: Optional file being generated
            language: Optional programming language
            
        Returns:
            bool: True if sent successfully
        """
        payload = {"token": token}
        if file_path:
            payload["file_path"] = file_path
        if language:
            payload["language"] = language
            
        return await self.send_message(user_id, {
            "type": "code_token",
            "payload": payload
        })
    
    async def send_sandbox_status(
        self,
        user_id: str,
        stage: str,
        message_text: str,
        sandbox_id: Optional[str] = None,
        logs: Optional[List[str]] = None,
        progress: Optional[int] = None
    ) -> bool:
        """
        Send E2B sandbox deployment status.
        
        Args:
            user_id: Target user ID
            stage: Deployment stage (creating, deploying, installing, starting, ready, error)
            message_text: Human-readable status
            sandbox_id: E2B sandbox ID
            logs: Recent sandbox logs
            progress: Progress percentage
            
        Returns:
            bool: True if sent successfully
        """
        message = WSMessageFactory.sandbox_status(
            stage=stage,
            message=message_text,
            sandbox_id=sandbox_id,
            logs=logs,
            progress=progress
        )
        return await self.send_message(user_id, message)
    
    async def send_sandbox_log(
        self,
        user_id: str,
        log_line: str,
        stream: str = "stdout",  # stdout or stderr
        project_id: Optional[str] = None
    ) -> bool:
        """
        Send live sandbox execution log line.
        
        Args:
            user_id: Target user ID
            log_line: The log content
            stream: stdout or stderr
            project_id: E2B project/sandbox ID
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "sandbox_log",
            "payload": {
                "log": log_line,
                "stream": stream,
                "project_id": project_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_conversation_turn(
        self,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send conversation history entry.
        
        Args:
            user_id: Target user ID
            role: user, assistant, or system
            content: Message content
            metadata: Additional metadata
            
        Returns:
            bool: True if sent successfully
        """
        message = WSMessageFactory.conversation_turn(role, content, metadata)
        return await self.send_message(user_id, message)
    
    def get_connection_count(self) -> int:
        """Get number of active connections"""
        return len(self.active_connections)
    
    def is_connected(self, user_id: str) -> bool:
        """Check if user is connected"""
        return user_id in self.active_connections
    
    
    async def send_scp_planning(
        self,
        user_id: str,
        planning_step: str,
        details: Optional[str] = None
    ) -> bool:
        """
        Send SCP planning step update for real-time visibility.
        
        Args:
            user_id: User identifier
            planning_step: Current planning step (analyzing, assessing_complexity, generating_architecture, etc.)
            details: Optional details about this step
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "scp_planning",
            "payload": {
                "step": planning_step,
                "details": details,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_agent_planning(
        self,
        user_id: str,
        agent_name: str,
        planning_step: str,
        current_file: Optional[str] = None,
        progress: Optional[int] = None
    ) -> bool:
        """
        Send agent planning/execution update for transparency.
        
        Args:
            user_id: User identifier
            agent_name: Name of executing agent (fullstack_agent, etc.)
            planning_step: What the agent is doing now
            current_file: File being generated
            progress: Optional progress percentage
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "agent_planning",
            "payload": {
                "agent": agent_name,
                "step": planning_step,
                "current_file": current_file,
                "progress": progress,
                "timestamp": datetime.utcnow().isoformat()
            }
        })
    
    async def send_file_tree_update(
        self,
        user_id: str,
        file_path: str,
        status: str = "processing"
    ) -> bool:
        """
        Send file tree update for live progress display.
        
        Args:
            user_id: User identifier
            file_path: File path being processed
            status: Status (processing, complete, error)
            
        Returns:
            bool: True if sent successfully
        """
        return await self.send_message(user_id, {
            "type": "file_tree_update",
            "payload": {
                "file_path": file_path,
                "status": status
            }
        })


# ============================================================================
# GLOBAL CONNECTION MANAGER INSTANCE
# ============================================================================
manager = ConnectionManager()
