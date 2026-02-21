"""
Fullstack Agent - Agentic Rewrite
Hub-orchestrated, QAP-based code generation

ARCHITECTURE:
- Hub decides call_count and scope for each call (AgentStrategy)
- Agent executes one scoped call at a time (called by generation_routes.py loop)
- Agent outputs QAP FileOperation objects (write/modify/delete)
- generation_routes.py executor processes operations
"""
import json
import structlog
from typing import Dict, Any, List, Optional
from langchain_cerebras import ChatCerebras
from langchain_core.messages import SystemMessage, HumanMessage
from motor.motor_asyncio import AsyncIOMotorDatabase

from rotation.key_manager import cerebras_pool
from config.settings import settings
from schemas.agent import AgentOutputSchema, KeyValuePair, DependenciesSchema, FileOperation
from schemas.scp import SCPSchema
from agents.fullstack_agent.prompts import FULLSTACK_AGENT_SYSTEM_PROMPT
from agents.fullstack_agent.tools import create_codebase_tools

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


def _merge_agent_outputs(*outputs: AgentOutputSchema) -> AgentOutputSchema:
    """Merge multiple AgentOutputSchema results from multi-call execution."""
    all_ops: List[FileOperation] = []
    all_written: List[str] = []
    all_modified: List[str] = []
    all_deleted: List[str] = []
    all_packages: List[str] = []
    last_route = "/"
    last_instructions = None
    last_error = None

    for out in outputs:
        all_ops.extend(out.file_operations)
        all_written.extend(out.files_written)
        all_modified.extend(out.files_modified)
        all_deleted.extend(out.files_deleted)
        all_packages.extend(out.new_packages)
        if out.primary_route and out.primary_route != "/":
            last_route = out.primary_route
        if out.instructions:
            last_instructions = out.instructions
        if out.error:
            last_error = out.error

    merged_deps = _merge_dependencies(*[o.dependencies for o in outputs])
    merged_env = _merge_key_value_lists(*[o.environment_variables for o in outputs])

    return AgentOutputSchema(
        file_operations=all_ops,
        files_written=list(dict.fromkeys(all_written)),  # deduplicate preserving order
        files_modified=list(dict.fromkeys(all_modified)),
        files_deleted=list(dict.fromkeys(all_deleted)),
        new_packages=list(dict.fromkeys(all_packages)),
        dependencies=merged_deps,
        environment_variables=merged_env,
        primary_route=last_route,
        instructions=last_instructions,
        error=last_error
    )


# ============================================================================
# FULLSTACK AGENT
# ============================================================================

class FullstackAgent:
    """
    Fullstack Agent - Hub-Orchestrated, QAP-Based

    Each call is scoped by the Hub (AgentStrategy) and outputs QAP FileOperation objects.
    generation_routes.py orchestrates multi-call execution and applies operations.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.model = settings.cerebras_model
        self.tools = create_codebase_tools(db)
        logger.info(
            "fullstack_agent_initialized",
            model=self.model,
            tool_count=len(self.tools),
            framework="langchain",
            pattern="qap_operations"
        )

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    async def execute_scoped(
        self,
        scp: Dict[str, Any],
        task_type: str,
        scope: str,
        call_number: int = 1,
        context_from_previous: Optional[str] = None,
        key_concerns: Optional[List[str]] = None,
        project_id: Optional[str] = None,
    ) -> AgentOutputSchema:
        """
        Execute one scoped agent call as directed by the Hub's AgentStrategy.

        Args:
            scp: Full SCP from Central Hub
            task_type: "new_project" or "follow_up"
            scope: Exact files this call must generate (from AgentStrategy.calls[n].scope)
            call_number: Which call this is (1, 2, or 3) for context injection
            context_from_previous: Summary of files generated in prior calls
            key_concerns: Hub-specified critical constraints for this project
            project_id: Project ID (used if tools needed for follow-ups)

        Returns:
            AgentOutputSchema with QAP file_operations list
        """
        logger.info(
            "executing_scoped_call",
            call_number=call_number,
            task_type=task_type,
            scope_preview=scope[:100]
        )

        try:
            structured_llm = self._get_structured_llm()
            system_prompt = FULLSTACK_AGENT_SYSTEM_PROMPT

            user_prompt = self._build_scoped_user_prompt(
                scp=scp,
                task_type=task_type,
                scope=scope,
                call_number=call_number,
                context_from_previous=context_from_previous,
                key_concerns=key_concerns or []
            )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            logger.debug("invoking_cerebras", call_number=call_number)
            result: AgentOutputSchema = await structured_llm.ainvoke(messages)

            logger.info(
                "scoped_call_complete",
                call_number=call_number,
                operations=len(result.file_operations),
                new_packages=len(result.new_packages),
                has_error=bool(result.error)
            )

            return result

        except Exception as e:
            logger.exception("scoped_call_failed", call_number=call_number, error=str(e))
            return AgentOutputSchema(error=f"Agent call {call_number} failed: {str(e)}")

    async def execute(
        self,
        scp: Dict[str, Any],
        task_type: str = "new_project",
        project_id: Optional[str] = None,
        use_tools: bool = True
    ) -> AgentOutputSchema:
        """
        Legacy single-call execute. Used by handle_code_modification for simple follow-ups.
        For new projects, generation_routes.py calls execute_scoped() in a Hub-driven loop.
        """
        scope = "Generate all required files for this request"
        if task_type == "follow_up":
            scope = (
                "Apply the follow-up changes: use `modify` operations for existing files, "
                "`write` only for truly new files. Be surgical — only touch what changed."
            )

        return await self.execute_scoped(
            scp=scp,
            task_type=task_type,
            scope=scope,
            call_number=1,
            project_id=project_id,
        )

    # ========================================================================
    # PRIVATE: LLM SETUP + PROMPT BUILDING
    # ========================================================================

    def _get_structured_llm(self):
        """Build Cerebras LLM with structured output for AgentOutputSchema."""
        api_key = cerebras_pool.get_next_key()
        llm = ChatCerebras(
            model=self.model,
            api_key=api_key,
            max_tokens=16000,
            temperature=0.3,
        )
        return llm.with_structured_output(AgentOutputSchema)

    def _build_scoped_user_prompt(
        self,
        scp: Dict[str, Any],
        task_type: str,
        scope: str,
        call_number: int,
        context_from_previous: Optional[str],
        key_concerns: List[str]
    ) -> str:
        """Build user prompt with explicit scope injection from Hub's AgentStrategy."""
        scp_json = json.dumps(scp, indent=2)
        parts = []

        # --- Call Scope (from Hub orchestrator) ---
        parts.append(f"## Call Scope (Call {call_number})\n")
        parts.append(f"Generate ONLY these files/operations:\n{scope}\n")
        parts.append("Do not generate files outside this scope.\n")

        # --- Key Concerns (Hub-specified constraints) ---
        if key_concerns:
            parts.append("## Key Concerns\n")
            for concern in key_concerns:
                parts.append(f"- {concern}\n")
            parts.append("\n")

        # --- Context from previous calls ---
        if context_from_previous:
            parts.append("## Files Generated in Previous Calls\n")
            parts.append(context_from_previous)
            parts.append("\nImport from these files where needed. Do not regenerate them.\n\n")

        # --- SCP ---
        parts.append(f"## Structured Context Protocol\n```json\n{scp_json}\n```\n")

        # --- Task type specific ---
        if task_type == "follow_up":
            parts.append(
                "**FOLLOW-UP MODE**: Use `modify` operations for existing files, "
                "`write` only for truly new files. Be surgical — only touch what changed.\n"
            )
        else:
            parts.append(
                "**NEW PROJECT**: Use `write` operations for ALL files. "
                "Complete file content required — no placeholders.\n"
            )

        return "\n".join(parts)

    def _format_operations_as_context(self, result: AgentOutputSchema) -> str:
        """Format generated operations as context summary for the next agent call."""
        lines = []
        for op in result.file_operations:
            if op.operation == "write":
                lines.append(f"- CREATED: {op.path}")
            elif op.operation == "modify":
                lines.append(f"- MODIFIED: {op.path}")
            elif op.operation == "delete":
                lines.append(f"- DELETED: {op.path}")
        return "\n".join(lines) if lines else "(no files from previous calls)"



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

    Raises:
        RuntimeError: If agent not initialized
    """
    if fullstack_agent is None:
        raise RuntimeError("Fullstack Agent not initialized. Call initialize_agent() first.")
    return fullstack_agent
