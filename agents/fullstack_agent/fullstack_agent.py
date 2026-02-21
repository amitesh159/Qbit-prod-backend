"""
Fullstack Agent - Complete Refactor
Production-Ready LangChain Agent with Tool Integration
Clean Code by Senior Python + LangChain Expert

ARCHITECTURE:
- Central Hub generates SCP → Fullstack Agent executes with tools
- 1-3 API calls based on complexity (NOT multi-turn loop),
- LangChain tools for codebase memory and context
- Proper error handling, logging, and validation
"""
import json
import structlog
from typing import Dict, Any, List, Optional, AsyncIterator
from pydantic import ValidationError
from langchain_cerebras import ChatCerebras
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from motor.motor_asyncio import AsyncIOMotorDatabase

from rotation.key_manager import cerebras_pool
from config.settings import settings
from schemas.agent import FileSchema, AgentOutputSchema, KeyValuePair, DependenciesSchema  # Import from shared schemas
from schemas.scp import SCPSchema  # Import SCP schema
from agents.fullstack_agent.prompts import FULLSTACK_AGENT_SYSTEM_PROMPT
from agents.fullstack_agent.tools import create_codebase_tools, TOOL_USAGE_EXAMPLES

logger = structlog.get_logger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _merge_key_value_lists(*lists: List[KeyValuePair]) -> List[KeyValuePair]:
    """Merge multiple List[KeyValuePair], later values override earlier ones."""
    merged_dict = {}
    for kv_list in lists:
        for item in kv_list:
            merged_dict[item.key] = item.value
    return [KeyValuePair(key=k, value=v) for k, v in merged_dict.items()]


def _merge_dependencies(*deps: DependenciesSchema) -> DependenciesSchema:
    """Merge multiple DependenciesSchema objects."""
    all_frontend = [d.frontend for d in deps]
    all_backend = [d.backend for d in deps]
    return DependenciesSchema(
        frontend=_merge_key_value_lists(*all_frontend),
        backend=_merge_key_value_lists(*all_backend)
    )


# ============================================================================
# OUTPUT SCHEMAS - Now imported from schemas.agent
# ============================================================================
# FileSchema and AgentOutputSchema are now in schemas/agent.py


# ============================================================================
# FULLSTACK AGENT 
# ============================================================================

class FullstackAgent:
    """
    Elite Fullstack Agent with LangChain Tools Integration
    
    **Philosophy**: Clean, maintainable, production-ready code
    
    **Capabilities**:
    - Reads existing codebase before modifications (tools)
    - Generates complete files, not placeholders
    - 1-3 API calls based on complexity
    - Streams tokens for real-time frontend display
    - Proper error handling and fallbacks
    
    **Tools** (for follow-ups):
    - read_project_files: Read existing files
    - search_codebase: Find patterns with regex
    - list_project_files: Explore structure
    - get_project_overview: Architecture context
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize Fullstack Agent with database for tools.
        
        Args:
            db: MongoDB database for Knowledge Base access
        """
        self.db = db
        self.model = settings.cerebras_model  # qwen-3-32b for fast generation
        self.tools = create_codebase_tools(db)
        
        logger.info(
            "fullstack_agent_initialized",
            model=self.model,
            tool_count=len(self.tools),
            framework="langchain",
            pattern="with_structured_output"
        )
    
    # ========================================================================
    # PUBLIC API - MAIN EXECUTION METHODS
    # ========================================================================
    
    async def execute(
        self,
        scp: Dict[str, Any],
        task_type: str = "new_project",
        project_id: Optional[str] = None,
        use_tools: bool = True
    ) -> AgentOutputSchema:
        """
        Execute SCP with LangChain integration.
        
        **Workflow**:
        1. Analyze complexity from SCP
        2. If follow-up + use_tools: Use tools to read existing code
        3. Make 1-3 API calls based on complexity
        4. Parse and validate output
        5. Return structured result
        
        Args:
            scp: Structured Context Protocol from Central Hub
            task_type: "new_project" or "follow_up"
            project_id: Project ID (required for follow-ups with tools)
            use_tools: Whether to use LangChain tools for codebase access
            
        Returns:
            AgentOutputSchema: Validated output with files, dependencies, instructions
        """
        complexity = scp.get("complexity", "moderate")
        
        logger.info(
            "executing_scp",
            task_type=task_type,
            complexity=complexity,
            use_tools=use_tools and task_type == "follow_up",
            project_id=project_id
        )
        
        try:
            # Step 1: Gather context using tools (for follow-ups)
            tool_context = ""
            if use_tools and task_type == "follow_up" and project_id:
                tool_context = await self._gather_context_with_tools(scp, project_id)
            
            # Step 2: Execute based on complexity (1-3 API calls)
            if complexity == "simple":
                result = await self._single_call_generation(scp, task_type, tool_context)
            elif complexity == "moderate":
                result = await self._two_call_generation(scp, task_type, tool_context)
            else:  # complex
                result = await self._three_call_generation(scp, task_type, tool_context)
            
            # Step 3: Validate and post-process
            result = self._post_process_result(result, scp)
            
            logger.info(
                "execution_complete",
                file_count=len(result.files),
                has_error=bool(result.error)
            )
            
            return result
            
        except Exception as e:
            logger.exception("execution_failed", error=str(e))
            return AgentOutputSchema(
                files=[],
                dependencies={},
                error=f"Execution failed: {str(e)}"
            )
    
    async def execute_streaming(
        self,
        scp: Dict[str, Any],
        task_type: str = "new_project",
        project_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """
        Execute with streaming using LangChain structured output.
        
        LangChain's with_structured_output() handles:
        - Schema conversion to Cerebras json_schema format
        - Automatic thinking tag hiding (reasoning_format='hidden')
        - Progressive JSON streaming or complete object streaming
        
        Args:
            scp: Structured Context Protocol
            task_type: "new_project" or "follow_up"
            project_id: Project ID
            
        Yields:
            JSON string chunks (structured output)
        """
        api_key = cerebras_pool.get_next_key()
        
        try:
            # Create base LLM - NO manual response_format!
            llm = ChatCerebras(
                model=self.model,
                api_key=api_key,
                temperature=0.1,
                streaming=True,
                max_tokens=40000,  # Explicitly set to support zai-glm-4.7 capacity
                request_timeout=600  # 10 minutes timeout to prevent 504 errors
            )
            
            # Apply structured output - LangChain handles schema automatically
            structured_llm = llm.with_structured_output(
                AgentOutputSchema,
                method="json_schema"
            )
            
            # Build prompts
            system_prompt = self._build_system_prompt(use_structured_output=True)
            user_prompt = self._build_user_prompt(scp, task_type, tool_context="")
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            logger.info("streaming_started", task_type=task_type, model=self.model)
            
            # Stream from structured LLM
            # LangChain may return progressive JSON strings or complete objects
            async for chunk in structured_llm.astream(messages):
                # Handle different chunk types
                if isinstance(chunk, str):
                    # JSON string chunk
                    yield chunk
                elif hasattr(chunk, 'content') and chunk.content:
                    # AIMessage chunk with content
                    yield chunk.content
                elif isinstance(chunk, dict):
                    # Dict chunk - serialize to JSON
                    yield json.dumps(chunk)
                elif isinstance(chunk, AgentOutputSchema):
                    # Complete Pydantic object - serialize
                    yield chunk.model_dump_json()
            
            logger.info("streaming_complete")
            
        except Exception as e:
            logger.exception("streaming_failed", error=str(e))
            cerebras_pool.mark_unhealthy(api_key, e)
            
            # Return error in proper format
            error_json = json.dumps({
                "files": [],
                "dependencies": {},
                "error": f"Streaming failed: {str(e)}"
            })
            yield error_json
    
    # ========================================================================
    # STRUCTURED OUTPUT HELPER
    # ========================================================================
    
    def _get_structured_llm(self):
        """
        Create LLM with structured output enforcement.
        
        LangChain's with_structured_output() handles ALL schema preparation:
        - Converts Pydantic model to JSON schema
        - Constructs response_format for Cerebras
        - Preserves all required fields (default, anyOf, etc.)
        - Returns LLM that outputs validated Pydantic objects
        
        Returns:
            LLM configured to output AgentOutputSchema directly
        """
        api_key = cerebras_pool.get_next_key()
        
        # Create base LLM - NO manual response_format in model_kwargs!
        llm = ChatCerebras(
            model=self.model,
            api_key=api_key,
            temperature=0.1,
            max_tokens=40000,  # Explicitly set to support zai-glm-4.7 capacity
            request_timeout=600  # 10 minutes timeout
        )
        
        # Let LangChain handle schema conversion and configuration
        # method="json_schema" uses Cerebras native structured output support
        structured_llm = llm.with_structured_output(
            AgentOutputSchema,
            method="json_schema"
        )
        
        logger.debug("structured_llm_created", model=self.model, method="json_schema")
        return structured_llm
    
    # ========================================================================
    # CONTEXT GATHERING WITH TOOLS (Follow-Ups)
    # ========================================================================
    
    async def _gather_context_with_tools(
        self,
        scp: Dict[str, Any],
        project_id: str
    ) -> str:
        """
        Use LangChain tools to gather context for follow-up modifications.
        
        **Strategy**:
        1. Get project overview (architecture, stack, patterns)
        2. Read affected files mentioned in SCP
        3. Search for relevant patterns if needed
        
        Args:
            scp: SCP containing requested changes
            project_id: Project ID
            
        Returns:
            Formatted context string with tool results
        """
        context_parts = []
        
        try:
            # Tool 1: Get project overview
            from agents.fullstack_agent.tools import CodebaseTools
            tools = CodebaseTools(self.db)
            
            overview = await tools.get_project_context(project_id, max_tokens=3000)
            context_parts.append(f"## Project Overview\n{overview}\n")
            
            # Tool 2: Read affected files (if specified in SCP)
            affected_files = scp.get("existing_context", {}).get("affected_files", [])
            if affected_files:
                file_contents = await tools.read_files(affected_files[:5], project_id)
                context_parts.append(f"## Existing Files\n{file_contents}\n")
            
            # Tool 3: Search for patterns (if modifying specific features)
            features = scp.get("features", [])
            if features:
                # Search for first feature to understand existing implementation
                feature_name = features[0].get("name", "")
                if feature_name:
                    search_results = await tools.search_codebase(
                        query=feature_name.replace(" ", ".*"),
                        project_id=project_id
                    )
                    context_parts.append(f"## Related Code\n{search_results}\n")
            
            tool_summary = f"Used {len(context_parts)} tools: get_project_overview, read_files, search_codebase"
            context_parts.insert(0, f"**Tool Usage**: {tool_summary}\n\n")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.exception("tool_context_gathering_failed", error=str(e))
            return "⚠️ Failed to gather context with tools"
    
    # ========================================================================
    # EXECUTION STRATEGIES (1-3 API Calls)
    # ========================================================================
    
    async def _single_call_generation(
        self,
        scp: Dict[str, Any],
        task_type: str,
        tool_context: str
    ) -> AgentOutputSchema:
        """
        1 API call - Generate all files at once using with_structured_output().
        Used for simple projects (<5 files, no backend).
        
        Args:
            scp: SCP
            task_type: new_project or follow_up
            tool_context: Context from tools
            
        Returns:
            AgentOutputSchema (guaranteed valid by LangChain)
        """
        logger.info("strategy", calls=1, complexity="simple", method="with_structured_output")
        
        try:
            # Get LLM with structured output
            structured_llm = self._get_structured_llm()
            
            # Build prompts (simplified - no JSON format instructions needed)
            system_prompt = self._build_system_prompt()
            user_prompt = self._build_user_prompt(scp, task_type, tool_context, phase="all")
            
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            # Log what we're sending
            logger.info(
                "calling_cerebras",
                scp_overview=scp.get("project_overview", "")[:100],
                complexity=scp.get("complexity"),
                message_count=len(messages)
            )
            
            # Returns validated Pydantic object directly - no parsing needed!
            result = await structured_llm.ainvoke(messages)
            
            # Log what we got back
            logger.info(
                "cerebras_response",
                file_count=len(result.files),
                has_dependencies=bool(result.dependencies),
                has_error=bool(result.error),
                error_msg=result.error if result.error else None
            )
            
            logger.info(
                "generation_complete",
                file_count=len(result.files),
                has_dependencies=bool(result.dependencies),
                has_error=bool(result.error)
            )
            
            return result
                
        except Exception as e:
            logger.exception("single_call_failed", error=str(e))
            # Return error in structured format
            return AgentOutputSchema(files=[], error=str(e))
    
    async def _two_call_generation(
        self,
        scp: Dict[str, Any],
        task_type: str,
        tool_context: str
    ) -> AgentOutputSchema:
        """
        2 API calls with structured output for each call.
        
        Call 1: Config, schemas, types, utilities
        Call 2: Components, pages, API routes (with context from Call 1)
        
        Args:
            scp: SCP
            task_type: new_project or follow_up
            tool_context: Context from tools
            
        Returns:
            AgentOutputSchema
        """
        logger.info("strategy", calls=2, complexity="moderate")
        
        try:
            # Use structured LLM for both calls
            structured_llm = self._get_structured_llm()
            
            # Build system prompt (no format instructions needed)
            system_prompt = self._build_system_prompt(use_structured_output=True)
            
            # Call 1: Structure
            user_prompt_1 = self._build_user_prompt(
                scp, task_type, tool_context,
                phase="structure",
                context="Generate project structure: package.json, tsconfig, types, utils, schemas"
            )
            
            messages_1 = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt_1)
            ]
            
            result_1 = await structured_llm.ainvoke(messages_1)  # Returns AgentOutputSchema
            
            # Call 2: Implementation (with context from Call 1)
            structure_summary = self._format_files_summary(result_1.files)
            user_prompt_2 = self._build_user_prompt(
                scp, task_type, tool_context,
                phase="implementation",
                context=f"Generate implementation. Existing structure:\n{structure_summary}"
            )
            
            messages_2 = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt_2)
            ]
            
            result_2 = await structured_llm.ainvoke(messages_2)  # Returns AgentOutputSchema
            
            # Merge results
            return AgentOutputSchema(
                files=result_1.files + result_2.files,
                dependencies=_merge_dependencies(result_1.dependencies, result_2.dependencies),
                environment_variables=_merge_key_value_lists(
                    result_1.environment_variables,
                    result_2.environment_variables
                ),
                instructions=result_2.instructions or result_1.instructions
            )
            
        except Exception as e:
            logger.exception("two_call_failed", error=str(e))
            return AgentOutputSchema(files=[], error=str(e))
    
    async def _three_call_generation(
        self,
        scp: Dict[str, Any],
        task_type: str,
        tool_context: str
    ) -> AgentOutputSchema:
        """
        3 API calls with structured output for each call.
        
        Call 1: Backend (API, database, services)
        Call 2: Frontend (components, pages) with backend API context
        Call 3: Polish (animations, optimizations, error handling)
        
        Args:
            scp: SCP
            task_type: new_project or follow_up
            tool_context: Context from tools
            
        Returns:
            AgentOutputSchema
        """
        logger.info("strategy", calls=3, complexity="complex")
        
        try:
            # Use structured LLM for all calls
            structured_llm = self._get_structured_llm()
            
            # Build system prompt (no format instructions needed)
            system_prompt = self._build_system_prompt(use_structured_output=True)
            
            # Call 1: Backend
            user_prompt_1 = self._build_user_prompt(
                scp, task_type, tool_context,
                phase="backend",
                context="Generate BACKEND files only: API routes, database models, services, middleware"
            )
            
            result_1 = await structured_llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt_1)
            ])  # Returns AgentOutputSchema
            
            # Call 2: Frontend (with backend context)
            backend_api_summary = self._extract_api_routes(result_1.files)
            user_prompt_2 = self._build_user_prompt(
                scp, task_type, tool_context,
                phase="frontend",
                context=f"Generate FRONTEND files. Backend API endpoints:\n{backend_api_summary}"
            )
            
            result_2 = await structured_llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt_2)
            ])  # Returns AgentOutputSchema
            
            # Call 3: Polish
            all_files_summary = self._format_files_summary(result_1.files + result_2.files)
            user_prompt_3 = self._build_user_prompt(
                scp, task_type, tool_context,
                phase="polish",
                context=f"Add polish: animations (Framer Motion, GSAP), error boundaries, loading states, optimizations.\nExisting files:\n{all_files_summary}"
            )
            
            result_3 = await structured_llm.ainvoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt_3)
            ])  # Returns AgentOutputSchema
            
            # Merge results
            return AgentOutputSchema(
                files=result_1.files + result_2.files + result_3.files,
                dependencies=_merge_dependencies(
                    result_1.dependencies,
                    result_2.dependencies,
                    result_3.dependencies
                ),
                environment_variables=_merge_key_value_lists(
                    result_1.environment_variables,
                    result_2.environment_variables,
                    result_3.environment_variables
                ),
                instructions=result_3.instructions or result_2.instructions or result_1.instructions,
                tool_usage_summary="Used 3 API calls: backend → frontend → polish"
            )
            
        except Exception as e:
            logger.exception("three_call_failed", error=str(e))
            return AgentOutputSchema(files=[], error=str(e))
    
    # ========================================================================
    # PROMPT BUILDING
    # ========================================================================
    
    def _build_system_prompt(self, use_structured_output: bool = True) -> str:
        """
        Build system prompt.
        
        Args:
            use_structured_output: If True, assumes LLM has with_structured_output() applied.
                                   If False, adds JSON format instructions for raw output.
        """
        if use_structured_output:
            # with_structured_output() handles schema enforcement
            # Just return base prompt
            return FULLSTACK_AGENT_SYSTEM_PROMPT
        
        # Fallback for streaming/raw mode - add manual JSON instructions
        return f"""{FULLSTACK_AGENT_SYSTEM_PROMPT}

## Output Format

You MUST respond with valid JSON matching this schema:

```json
{{
  "files": [
    {{
      "path": "/frontend/app/page.tsx",
      "content": "...",
      "action": "create"
    }}
  ],
  "dependencies": {{
    "frontend": {{}},
    "backend": {{}}
  }},
  "environment_variables": {{}},
  "instructions": "Optional setup instructions"
}}
```

**CRITICAL RULES**:
1. Output ONLY valid JSON (no markdown, no thinking tags)
2. All file paths start with `/frontend/` or `/backend/`
3. Complete file content - NO placeholders
"""
    
    def _build_user_prompt(
        self,
        scp: Dict[str, Any],
        task_type: str,
        tool_context: str,
        phase: str = "all",
        context: str = ""
    ) -> str:
        """Build user prompt with SCP and context."""
        scp_json = json.dumps(scp, indent=2)
        
        parts = []
        
        # Tool context (if any)
        if tool_context:
            parts.append(f"## Context from Tools\n{tool_context}\n")
        
        # Phase instruction
        parts.append(f"## Phase: {phase.upper()}\n{context}\n")
        
        # SCP
        parts.append(f"## Structured Context Protocol\n```json\n{scp_json}\n```\n")
        
        # Task type specific instructions
        if task_type == "follow_up":
            parts.append(
                "**CRITICAL**: Generate ONLY changed/new files. "
                "Do not regenerate unchanged files. Use minimal diffs.\n"
            )
        else:
            parts.append(
                "**CRITICAL**: Generate COMPLETE files with no placeholders. "
                "All paths must start with /frontend/ or /backend/.\n"
            )
        
        return "\n".join(parts)
    
    # ========================================================================
    # PARSING & VALIDATION
    # ========================================================================
    
    # Immutable template files - LLM must NEVER overwrite these
    IMMUTABLE_TEMPLATE_FILES = frozenset({
        "/frontend/package.json",
        "/frontend/package-lock.json",
        "/frontend/tsconfig.json",
        "/frontend/next.config.ts",
        "/frontend/postcss.config.mjs",
        "/frontend/components.json",
        "/frontend/eslint.config.mjs",
        "/frontend/next-env.d.ts",
        "/frontend/lib/utils.ts",
        "/frontend/hooks/use-mobile.ts",
        "/frontend/app/favicon.ico",
    })
    
    def _post_process_result(
        self,
        result: AgentOutputSchema,
        scp: Dict[str, Any]
    ) -> AgentOutputSchema:
        """
        Post-process result to ensure quality.
        
        - Validate file paths start with /frontend/ or /backend/
        - Strip immutable template files the LLM may have generated
        - Strip files targeting /frontend/components/ui/ (pre-installed)
        - Detect truncated/incomplete files
        - Add default instructions if missing
        """
        # Filter: valid paths only
        result.files = [
            f for f in result.files
            if f.path.startswith(("/frontend/", "/backend/"))
        ]
        
        # Filter: remove immutable template files
        before_count = len(result.files)
        result.files = [
            f for f in result.files
            if f.path not in self.IMMUTABLE_TEMPLATE_FILES
        ]
        
        # Filter: remove any files targeting pre-installed shadcn/ui components
        result.files = [
            f for f in result.files
            if not f.path.startswith("/frontend/components/ui/")
        ]
        
        stripped_count = before_count - len(result.files)
        if stripped_count > 0:
            logger.warning(
                "stripped_immutable_files",
                count=stripped_count,
                remaining=len(result.files)
            )
        
        # Validate: detect truncated files
        truncated_files = []
        for file in result.files:
            content = file.content.rstrip()
            
            # Skip non-code files
            if not file.path.endswith(('.tsx', '.ts', '.jsx', '.js', '.css')):
                continue
            
            # Check 1: Incomplete JSX tags (e.g., "<h3 className=" with no closing)
            if '<' in content and not content.endswith('>'):
                last_50 = content[-50:]
                if '<' in last_50 and '>' not in last_50:
                    truncated_files.append((file.path, "incomplete JSX tag"))
                    continue
            
            # Check 2: Unclosed braces/brackets/parens
            brace_balance = content.count('{') - content.count('}')
            bracket_balance = content.count('[') - content.count(']')
            paren_balance = content.count('(') - content.count(')')
            
            if abs(brace_balance) > 2 or abs(bracket_balance) > 2 or abs(paren_balance) > 2:
                truncated_files.append((file.path, f"unbalanced delimiters: {{:{brace_balance} [:{bracket_balance} (:{paren_balance}"))
                continue
            
            # Check 3: File ends mid-statement (e.g., ends with "=", "className=", "import {")
            suspicious_endings = ['=', '{', '(', '[', ',', 'className=', 'import {', 'from "']
            if any(content.rstrip().endswith(ending) for ending in suspicious_endings):
                truncated_files.append((file.path, "ends mid-statement"))
                continue
            
            # Check 4: TypeScript/JSX files that are suspiciously short (< 10 lines)
            # This catches files where generation started but stopped early
            if file.path.endswith(('.tsx', '.jsx')):
                line_count = content.count('\n') + 1
                if line_count < 10 and 'export' in content:
                    # Has export but is very short - likely truncated
                    truncated_files.append((file.path, f"suspiciously short: {line_count} lines"))
        
        if truncated_files:
            logger.error(
                "truncated_files_detected",
                count=len(truncated_files),
                files=truncated_files
            )
            # Set error to inform user
            truncation_summary = "\n".join([f"- {path}: {reason}" for path, reason in truncated_files])
            result.error = f"Code generation incomplete - {len(truncated_files)} files truncated:\n{truncation_summary}\n\nThis is a token limit issue. Try simplifying the request or reducing features."
        
        # Default instructions
        if not result.instructions and not result.error:
            result.instructions = "Run `npm run dev` to start the development server"
        
        return result
    
    # ========================================================================
    # UTILITIES
    # ========================================================================
    
    def _format_files_summary(self, files: List[FileSchema]) -> str:
        """Format files as summary for context in next call."""
        return "\n".join([f"- {f.path}" for f in files[:20]])
    
    def _extract_api_routes(self, files: List[FileSchema]) -> str:
        """Extract API routes from backend files."""
        routes = []
        for f in files:
            if "/api/" in f.path or "/routes/" in f.path:
                routes.append(f.path)
        return "\n".join(routes) if routes else "No API routes"


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================

# Will be initialized in main.py with database
fullstack_agent: Optional[FullstackAgent] = None

def initialize_agent(db: AsyncIOMotorDatabase) -> None:
    """Initialize global Fullstack Agent instance."""
    global fullstack_agent
    fullstack_agent = FullstackAgent(db)
    logger.info("fullstack_agent_initialized_global")


def get_fullstack_agent() -> FullstackAgent:
    """
    Get the global Fullstack Agent instance.
    
    Returns:
        FullstackAgent: The initialized agent instance
        
    Raises:
        RuntimeError: If agent not initialized
    """
    if fullstack_agent is None:
        raise RuntimeError("Fullstack Agent not initialized. Call initialize_agent() first.")
    return fullstack_agent
