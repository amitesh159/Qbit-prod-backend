"""
Central Hub - Complete Rewrite from Scratch
The Brain of Qbit AI System

ARCHITECTURE: 1 API Call with Memory Integration
- Loads conversation history (cached - instant!)
- Loads project context (cached - instant!)
- Injects context into prompt
- Makes SINGLE Groq API call (ASYNC - non-blocking)
- Parses with Pydantic (robust validation)
- Saves to cache
- Returns structured output including agent_strategy

ROLE:
- Intent classification (code_generation|follow_up|conversation|discussion|ambiguous)
- SCP generation for code intents (complete specification)
- Agent strategy planning (call_count, scope per call, key_concerns)
- Direct responses for non-code intents
- Never generates code - delegates to FullStack Agent
"""
import structlog
import json
import re
from typing import Dict, Any, Optional, List
from groq import AsyncGroq  # Changed from Groq to AsyncGroq (non-blocking)
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, AIMessage

from rotation.key_manager import groq_pool
from memory.cached_conversation import CachedConversationMemory
from memory.project_store_cache import CachedProjectStore
from schemas.scp import CentralHubOutput, AgentStrategy, AgentCallScope
from config.settings import settings

logger = structlog.get_logger(__name__)


# ============================================================================
# CENTRAL HUB
# ============================================================================

class CentralHub:
    """
    The Brain - Decision Engine and Project Manager
    
    Complete rewrite with:
    1. ✅ 1 API call (not multi-turn agent loop)
    2. ✅ Cached memory (no DB on every message)
    3. ✅ Context injection (history + project)
    4. ✅ Pydantic validation (no regex hacks)
    5. ✅ Clean, maintainable code
    """
    
    # Intent types
    AGENT_INVOCATION_INTENTS = ["code_generation", "follow_up"]
    DIRECT_RESPONSE_INTENTS = ["conversation", "discussion", "ambiguous"]
    
    def __init__(
        self,
        memory: CachedConversationMemory,
        store: CachedProjectStore
    ):
        """
        Initialize Central Hub with memory.
        
        Args:
            memory: Cached conversation memory
            store: Cached project store
        """
        self.memory = memory
        self.store = store
        self.model = settings.groq_model
        
        logger.info(
            "central_hub_initialized",
            model=self.model,
            memory="cached",
            store="cached"
        )
    
    # ========================================================================
    # MAIN ENTRY - 1 API CALL
    # ========================================================================
    
    async def process_message(
        self,
        user_message: str,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
        discussion_mode: bool = False
    ) -> CentralHubOutput:
        """
        Process user message with SINGLE API call + memory.
        
        Workflow:
        1. Load history (cached - instant!)
        2. Load project context (cached - instant!)
        3. Build prompt with context injection
        4. Make 1 Groq API call
        5. Parse with Pydantic (robust validation)
        6. Save to cache
        7. Return result
        
        Args:
            user_message: User's natural language input
            project_id: Existing project ID (for follow-ups)
            user_id: User ID
            discussion_mode: Planning/discussion mode flag
            
        Returns:
            CentralHubOutput: Pydantic model with intent, response/SCP, complexity, etc.
        """
        logger.info(
            "processing_message",
            message_len=len(user_message),
            has_project=bool(project_id),
            discussion_mode=discussion_mode
        )
        
        try:
            # Step 1: Load conversation history (CACHED - instant!)
            history = []
            if project_id:
                history = await self.memory.get_history(project_id, max_messages=20)
            
            # Step 2: Load project context (CACHED - instant!)
            project_ctx = None
            if project_id:
                project_ctx = await self.store.get_context(
                    project_id=project_id,
                    user_intent=user_message
                )
            
            # Step 3: Build context-aware prompt
            system_prompt = self._build_system_prompt(history, project_ctx, discussion_mode)
            user_prompt = self._build_user_prompt(user_message, project_ctx)
            
            # Step 4: SINGLE ASYNC API CALL (non-blocking - uses AsyncGroq)
            api_key = groq_pool.get_next_key()
            client = AsyncGroq(api_key=api_key)  # AsyncGroq - won't block event loop
            
            logger.debug("making_groq_api_call", model=self.model)
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=16000,
                response_format={"type": "json_object"}  # Force valid JSON output
            )
            
            # Step 5: Parse with Pydantic (robust!)
            result_dict = self._parse_and_validate(response.choices[0].message.content, user_message)
            
            # Step 6: Save to cache
            if project_id  and result_dict.get("intent") not in ["ambiguous"]:
                await self.memory.add_message(project_id, HumanMessage(content=user_message))
                
                # Save assistant response
                response_content = result_dict.get("response", f"Intent: {result_dict['intent']}")
                await self.memory.add_message(project_id, AIMessage(content=response_content))
            
            logger.info(
                "processing_complete",
                intent=result_dict["intent"],
                complexity=result_dict.get("complexity"),
                tokens=response.usage.total_tokens if response.usage else None
            )
            
            # Step 6.5: Coerce to proper format before Pydantic validation
            result_dict = self._coerce_to_hub_output(result_dict)
            
            # Convert dict to Pydantic model for type safety
            return CentralHubOutput(**result_dict)
            
        except Exception as e:
            logger.exception("processing_failed", error=str(e))
            error_dict = self._error_response(str(e))
            return CentralHubOutput(**error_dict)
    
    # ========================================================================
    # PROMPT BUILDING (Context Injection)
    # ========================================================================
    
    def _build_system_prompt(
        self,
        history: List,
        project_ctx: Optional[Dict],
        discussion_mode: bool
    ) -> str:
        """
        Build system prompt with injected context.
        
        This is where the magic happens - context injection replaces
        multi-turn agent loops.
        """
        from hub.prompts import CENTRAL_HUB_SYSTEM_PROMPT
        
        parts = []
        
        # Base prompt with comprehensive PM guidance
        parts.append(CENTRAL_HUB_SYSTEM_PROMPT)
        
        # Inject conversation history (full content, not 150-char truncation)
        if history:
            parts.append("\n## 💬 Conversation History (Context Injection)\n")
            parts.append("Previous messages in this conversation:\n")
            for msg in history[-10:]:  # Last 10 messages
                if isinstance(msg, HumanMessage):
                    # Full content up to 500 chars (not 150 which was too truncated)
                    parts.append(f"**User**: {msg.content[:500]}\n")
                elif isinstance(msg, AIMessage):
                    parts.append(f"**Assistant**: {msg.content[:300]}\n")
            parts.append("\nUse this history to understand follow-up requests and provide consistent responses.\n")
        
        # Inject project context
        if project_ctx:
            parts.append("\n## 📦 Existing Project Context (For Follow-Ups)\n")
            parts.append("User has an existing project with the following details:\n\n")
            
            summary = project_ctx.get("summary", {})
            if summary:
                parts.append(f"**Architecture**: {summary.get('architecture', 'N/A')[:200]}\n")
                parts.append(f"**Tech Stack**: {', '.join(summary.get('stack', []))}\n")
             
            files = project_ctx.get("file_tree", [])
            if files:
                parts.append(f"**Total Files**: {len(files)}\n")
                parts.append(f"**Key Files**: {', '.join([f.get('path', '') for f in files[:8]])}\n")
                
                # Include key components for better context
                all_components = []
                for f in files:
                    all_components.extend(f.get("anchors", {}).get("components", []))
                if all_components:
                    parts.append(f"**Key Components**: {', '.join(list(set(all_components))[:10])}\n")
            
            parts.append("\n**For Follow-Up Intent:**\n")
            parts.append("- Include this existing structure in your SCP\n")
            parts.append("- Ensure compatibility with current tech stack\n")
            parts.append("- Specify which files to modify in SCP.existing_context\n")
            parts.append("- Aim for minimal changes that integrate smoothly\n")
        
        # Discussion mode override
        if discussion_mode:
            parts.append("\n## 🤔 Discussion Mode ACTIVE\n")
            parts.append("**The user is in planning/discussion mode.**\n\n")
            parts.append("Your approach:\n")
            parts.append("- Ask thoughtful clarifying questions\n")
            parts.append("- Explain architectural options and tradeoffs\n")
            parts.append("- Provide professional guidance\n")
            parts.append("- Discuss best practices\n")
            parts.append("- **DO NOT** invoke the fullstack_agent unless user explicitly confirms they want to proceed with implementation\n")
            parts.append("- Keep intent as `discussion`\n")
        
        return "\n".join(parts)
    
    def _build_user_prompt(self, message: str, project_ctx: Optional[Dict]) -> str:
        """Build user prompt."""
        context_type = "follow-up for existing project" if project_ctx else "new request"
        return f"User Message: {message}\n\nContext: This is a {context_type}."
    
    # ========================================================================
    # PARSING & VALIDATION (Pydantic)
    # ========================================================================
    
    def _parse_and_validate(self, llm_output: str, user_message: str) -> Dict[str, Any]:
        """
        Parse and validate LLM output with robust error handling.
        
        Tries multiple parsing strategies:
        1. Direct JSON parsing
        2. JSON code block extraction
        3. Fallback to safe defaults
        """
        # Try parsing JSON
        result = None
        
        # Strategy 1: Direct JSON parse
        try:
            result = json.loads(llm_output.strip())
        except json.JSONDecodeError:
            pass
        
        # Strategy 2: Extract from code block
        if not result:
            json_match = re.search(r'```json\s*(\{[\s\S]*?\})\s*```', llm_output)
            if json_match:
                try:
                    result = json.loads(json_match.group(1))
                except json.JSONDecodeError:
                    pass
        
        # Strategy 3: Extract any JSON object
        if not result:
            json_match = re.search(r'\{[\s\S]*\}', llm_output)
            if json_match:
                try:
                    result = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass
        
        # Fallback if parsing failed
        if not result:
            logger.warning("failed_to_parse_llm_output", output_preview=llm_output[:200])
            return {
                "intent": "ambiguous",
                "response": "I had trouble understanding that. Could you please rephrase?",
                "agent_invocation": "none"
            }
        
        #  Validate and normalize
        return self._validate_output(result, user_message)
    
    def _validate_output(self, result: Dict[str, Any], user_message: str) -> Dict[str, Any]:
        """
        Validate output structure and business logic.
        
        Rules:
        - code_generation/follow_up MUST have SCP
        - conversation/discussion/ambiguous MUST have response
        - Set agent_invocation based on intent
        - Build default agent_strategy if not provided by LLM
        """
        # Ensure required fields exist
        normalized = {
            "intent": result.get("intent", "ambiguous"),
            "complexity": result.get("complexity"),
            "response": result.get("response"),
            "scp": result.get("scp"),
            "agent_invocation": result.get("agent_invocation", "none"),
            "reasoning": result.get("reasoning"),
            "agent_strategy": result.get("agent_strategy"),
        }
        
        # Validate: code intents must have SCP
        if normalized["intent"] in self.AGENT_INVOCATION_INTENTS:
            if not normalized["scp"]:
                logger.warning("code_intent_without_scp", intent=normalized["intent"])
                normalized["intent"] = "ambiguous"
                normalized["response"] = "I need more details. What type of application do you want to build?"
                normalized["agent_invocation"] = "none"
                normalized["agent_strategy"] = None
            else:
                normalized["agent_invocation"] = "fullstack_agent"
                # Build default agent_strategy if LLM didn't provide one
                if not normalized.get("agent_strategy"):
                    normalized["agent_strategy"] = self._build_default_strategy(
                        normalized["complexity"], normalized["intent"]
                    )
        else:
            normalized["agent_invocation"] = "none"
            normalized["agent_strategy"] = None
        
        # Validate: non-code intents should have response
        if normalized["intent"] in self.DIRECT_RESPONSE_INTENTS:
            if not normalized["response"]:
                normalized["response"] = "I'm here to help! What would you like to know?"
        
        return normalized
    
    def _build_default_strategy(self, complexity: Optional[str], intent: str) -> Dict[str, Any]:
        """
        Build a default AgentStrategy when the Hub LLM doesn't return one.
        Fallback: map complexity → call_count with generic scopes.
        """
        if complexity == "simple" or intent == "follow_up":
            return {
                "call_count": 1,
                "calls": [{"call_number": 1, "scope": "Generate all required files for this request"}],
                "needs_npm_install": False,
                "new_packages": [],
                "key_concerns": []
            }
        elif complexity == "moderate":
            return {
                "call_count": 2,
                "calls": [
                    {"call_number": 1, "scope": "Generate globals.css, layout.tsx, page.tsx, and core shared components"},
                    {"call_number": 2, "scope": "Generate feature components, hooks, and remaining pages"},
                ],
                "needs_npm_install": False,
                "new_packages": [],
                "key_concerns": []
            }
        else:  # complex
            return {
                "call_count": 3,
                "calls": [
                    {"call_number": 1, "scope": "Generate globals.css, layout.tsx, page.tsx, and core UI components"},
                    {"call_number": 2, "scope": "Generate feature components, data logic, and secondary pages"},
                    {"call_number": 3, "scope": "Generate backend API routes, server files, and integration code"},
                ],
                "needs_npm_install": False,
                "new_packages": [],
                "key_concerns": []
            }

    
    def _coerce_to_hub_output(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Coerce LLM output to match CentralHubOutput schema.
        
        Handles common LLM mistakes:
        - Comma-separated strings → lists
        - "none" strings → empty lists
        - Missing required fields
        
        This is a defensive layer before Pydantic validation.
        """
        # Deep copy to avoid mutating original
        import copy
        coerced = copy.deepcopy(result)
        
        # Helper: Convert string to list
        def str_to_list(value):
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
        
        # Fix SCP if present
        if "scp" in coerced and isinstance(coerced["scp"], dict):
            scp = coerced["scp"]
            
            # Fix tech_stack
            if "tech_stack" in scp and isinstance(scp["tech_stack"], dict):
                tech_stack = scp["tech_stack"]
                
                # Convert all tech_stack fields to lists
                for key in ["frontend", "backend", "ai_services"]:
                    if key in tech_stack:
                        tech_stack[key] = str_to_list(tech_stack[key])
                
                # Handle legacy "other" field
                if "other" in tech_stack:
                    if "ai_services" not in tech_stack:
                        tech_stack["ai_services"] = str_to_list(tech_stack["other"])
                    del tech_stack["other"]
            
            # Fix features (ensure it's a list of dicts)
            if "features" in scp:
                if isinstance(scp["features"], str):
                    # Can't easily parse string to features, set empty
                    scp["features"] = []
                elif not isinstance(scp["features"], list):
                    scp["features"] = []
            
            # Fix file_structure (ensure dict with lists)
            if "file_structure" in scp and isinstance(scp["file_structure"], dict):
                for key in ["frontend", "backend"]:
                    if key in scp["file_structure"]:
                        val = scp["file_structure"][key]
                        if isinstance(val, str):
                            scp["file_structure"][key] = str_to_list(val)
                        elif not isinstance(val, list):
                            scp["file_structure"][key] = []
            
            # Fix constraints
            if "constraints" in scp:
                scp["constraints"] = str_to_list(scp["constraints"])
        
        logger.debug("coercion_complete", has_scp=bool(coerced.get("scp")))
        return coerced
    
    # ========================================================================
    # ERROR HANDLING
    # ========================================================================
    
    def _error_response(self, error: str) -> Dict[str, Any]:
        """Generate safe error response that matches CentralHubOutput schema."""
        logger.warning("generating_error_response", error=error)
        return {
            "intent": "conversation",
            "response": "I encountered a technical issue. Please try again or rephrase your message.",
            "agent_invocation": "none"
            # Note: No "error" field - not in CentralHubOutput schema
        }


# ============================================================================
# GLOBAL INSTANCE (initialized in main.py lifespan)
# ============================================================================
central_hub: Optional[CentralHub] = None


async def initialize_hub(db):
    """
    Initialize Central Hub with memory.
    
    Called from main.py lifespan startup.
    
    Args:
        db: MongoDB database instance
    """
    global central_hub
    
    memory = CachedConversationMemory(db)
    store = CachedProjectStore(db)
    central_hub = CentralHub(memory, store)
    
    logger.info("global_central_hub_initialized")


def get_central_hub() -> CentralHub:
    """
    Get the global Central Hub instance.
    
    Returns:
        CentralHub: The initialized hub instance
        
    Raises:
        RuntimeError: If hub not initialized
    """
    if central_hub is None:
        raise RuntimeError("Central Hub not initialized. Call initialize_hub() first.")
    return central_hub


async def shutdown_hub():
    """
    Shutdown Central Hub - flush memory to DB.
    
    Called from main.py lifespan shutdown.
    """
    global central_hub
    
    if central_hub and central_hub.memory:
        await central_hub.memory.flush_all()
        logger.info("central_hub_shutdown_complete")
