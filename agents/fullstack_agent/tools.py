"""
LangChain Tools for Fullstack Agent
Production-ready tools inspired by v0.dev and lovable.dev patterns
"""
import structlog
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = structlog.get_logger(__name__)


# ============================================================================
# TOOL SCHEMAS (Pydantic Input Models)
# ============================================================================

class ReadFilesInput(BaseModel):
    """Input for reading multiple project files"""
    file_paths: List[str] = Field(
        description="List of file paths to read (relative to project root). "
                    "Examples: ['frontend/app/page.tsx', 'frontend/components/Header.tsx']"
    )
    project_id: str = Field(description="Project ID to read files from")


class SearchCodebaseInput(BaseModel):
    """Input for searching codebase with regex patterns"""
    query: str = Field(
        description="Regex pattern to search for in code. "
                    "Examples: 'function\\s+\\w+', 'import.*from', 'useState\\('"
    )
    project_id: str = Field(description="Project ID to search within")
    include_pattern: Optional[str] = Field(
        None,
        description="Glob pattern to include files (e.g., 'src/**/*.tsx', '*.py')"
    )
    exclude_pattern: Optional[str] = Field(
        None,
        description="Glob pattern to exclude files (e.g., '**/node_modules/**', '**/*.test.*')"
    )


class ListFilesInput(BaseModel):
    """Input for listing project file structure"""
    project_id: str = Field(description="Project ID to list files from")
    path: Optional[str] = Field(
        None,
        description="Optional subdirectory to list (relative to project root)"
    )
    glob_pattern: Optional[str] = Field(
        None,
        description="Optional glob pattern to filter files (e.g., '*.tsx', 'components/**')"
    )


class GetProjectContextInput(BaseModel):
    """Input for getting compressed project context"""
    project_id: str = Field(description="Project ID")
    max_tokens: int = Field(
        default=4000,
        description="Maximum tokens for compressed context"
    )


# ============================================================================
# CODEBASE TOOLS (Read-Only)
# ============================================================================

class CodebaseTools:
    """
    Read-only tools for exploring project codebase.
    Inspired by v0.dev's ReadFile, GrepRepo, LSRepo patterns.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        logger.info("codebase_tools_initialized")
    
    async def read_files(
        self,
        file_paths: List[str],
        project_id: str
    ) -> str:
        """
        Read multiple files from Knowledge Base.
        
        Similar to v0.dev's ReadFile tool - reads complete file contents
        for small files, or intelligently chunks large files.
        
        Args:
            file_paths: List of file paths to read
            project_id: Project ID
            
        Returns:
            Formatted string with file contents
        """
        try:
            from knowledge.kb_operations import get_file_content
            
            results = []
            for path in file_paths[:10]:  # Limit to 10 files
                try:
                    content = await get_file_content(project_id, path)
                    if content:
                        results.append(f"## File: {path}\n```\n{content}\n```\n")
                    else:
                        results.append(f"## File: {path}\n❌ Not found\n")
                except Exception as e:
                    results.append(f"## File: {path}\n❌ Error: {str(e)}\n")
            
            return "\n".join(results) if results else "No files found"
            
        except Exception as e:
            logger.exception("read_files_failed", error=str(e))
            return f"Error reading files: {str(e)}"
    
    async def search_codebase(
        self,
        query: str,
        project_id: str,
        include_pattern: Optional[str] = None,
        exclude_pattern: Optional[str] = None
    ) -> str:
        """
        Search codebase with regex patterns.
        
        Similar to v0.dev's GrepRepo and lovable.dev's lov-search-files.
        Returns matching lines with file paths and line numbers.
        
        Args:
            query: Regex pattern to search
            project_id: Project ID
            include_pattern: Glob to include files
            exclude_pattern: Glob to exclude files
            
        Returns:
            Formatted search results
        """
        try:
            from knowledge.kb_operations import search_in_project
            
            results = await search_in_project(
                project_id=project_id,
                search_query=query,
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern
            )
            
            if not results:
                return f"No matches found for pattern: {query}"
            
            # Format results
            output = [f"Found {len(results)} matches for: {query}\n"]
            for result in results[:50]:  # Limit to 50 results
                file_path = result.get("file")
                line_num = result.get("line_number")
                line_content = result.get("content", "").strip()
                
                output.append(f"{file_path}:{line_num}: {line_content}")
            
            if len(results) > 50:
                output.append(f"\n... and {len(results) - 50} more matches")
            
            return "\n".join(output)
            
        except Exception as e:
            logger.exception("search_codebase_failed", error=str(e))
            return f"Error searching codebase: {str(e)}"
    
    async def list_files(
        self,
        project_id: str,
        path: Optional[str] = None,
        glob_pattern: Optional[str] = None
    ) -> str:
        """
        List project file structure.
        
        Similar to v0.dev's LSRepo - returns file paths sorted alphabetically.
        
        Args:
            project_id: Project ID
            path: Optional subdirectory
            glob_pattern: Optional glob filter
            
        Returns:
            Formatted file listing
        """
        try:
            from knowledge.kb_operations import list_project_files
            
            files = await list_project_files(
                project_id=project_id,
                subdirectory=path,
                glob_pattern=glob_pattern
            )
            
            if not files:
                return "No files found"
            
            # Format as tree
            output = [f"Project file structure ({len(files)} files):\n"]
            for file_info in sorted(files, key=lambda x: x.get("path", ""))[:200]:
                file_path = file_info.get("path", "")
                size = file_info.get("size", 0)
                output.append(f"  {file_path} ({size} bytes)")
            
            if len(files) > 200:
                output.append(f"\n... and {len(files) - 200} more files")
            
            return "\n".join(output)
            
        except Exception as e:
            logger.exception("list_files_failed", error=str(e))
            return f"Error listing files: {str(e)}"
    
    async def get_project_context(
        self,
        project_id: str,
        max_tokens: int = 4000
    ) -> str:
        """
        Get compressed project context from Knowledge Base.
        
        Similar to v0.dev's SearchRepo with "Give me an overview" pattern.
        Returns high-level architecture, key files, and patterns.
        
        Args:
            project_id: Project ID
            max_tokens: Max tokens for context
            
        Returns:
            Compressed project overview
        """
        try:
            from knowledge.kb_operations import get_compressed_context
            
            context = await get_compressed_context(
                project_id=project_id,
                max_tokens=max_tokens
            )
            
            return context if context else "No project context available"
            
        except Exception as e:
            logger.exception("get_project_context_failed", error=str(e))
            return f"Error getting project context: {str(e)}"


# ============================================================================
# LANGCHAIN TOOL WRAPPERS
# ============================================================================

def create_codebase_tools(db: AsyncIOMotorDatabase) -> List[StructuredTool]:
    """
    Create LangChain tools for codebase operations.
    
    These tools allow the agent to:
    - Read existing files before modifying
    - Search for patterns, functions, imports
    - Explore project structure
    - Understand project architecture
    
    Returns:
        List of LangChain StructuredTool instances
    """
    tools_instance = CodebaseTools(db)
    
    tools = [
        StructuredTool(
            name="read_project_files",
            description=(
                "Read contents of multiple files from the project's Knowledge Base. "
                "Use this BEFORE making changes to understand existing code. "
                "\n\n**When to use:**\n"
                "- Before modifying files (understand current implementation)\n"
                "- Checking imports, dependencies, patterns\n"
                "- Understanding how features are currently implemented\n"
                "\n**Examples:**\n"
                "- Read ['frontend/app/layout.tsx', 'frontend/app/page.tsx']\n"
                "- Read ['frontend/components/ui/button.tsx'] to check component API"
            ),
            func=tools_instance.read_files,
            args_schema=ReadFilesInput,
            coroutine=tools_instance.read_files
        ),
        
        StructuredTool(
            name="search_codebase",
            description=(
                "Search project codebase with regex patterns. Returns matching lines "
                "with file paths and line numbers.\n"
                "\n**Common use cases:**\n"
                "- Find function definitions: 'function\\s+myFunction'\n"
                "- Locate imports: 'import.*from.*react'\n"
                "- Search for components: 'export.*function\\s+\\w+Component'\n"
                "- Find API calls: 'fetch\\(|axios\\.'  \n"
                "- Track usage: specific variable or function names\n"
                "\n**Examples:**\n"
                "- query='useState\\(' - Find all useState hooks\n"
                "- query='export.*Button' include_pattern='components/**' - Find Button exports in components"
            ),
            func=tools_instance.search_codebase,
            args_schema=SearchCodebaseInput,
            coroutine=tools_instance.search_codebase
        ),
        
        StructuredTool(
            name="list_project_files",
            description=(
                "List project file structure with optional filtering. "
                "Returns sorted file paths.\n"
                "\n**When to use:**\n"
                "- Explore project structure and layout\n"
                "- Find files in specific directories\n"
                "- Get overview before making changes\n"
                "\n**Examples:**\n"
                "- List all files in 'frontend/components/'\n"
                "- Use glob_pattern='*.tsx' to find all TypeScript React files\n"
                "- Use glob_pattern='frontend/app/**' to see routing structure"
            ),
            func=tools_instance.list_files,
            args_schema=ListFilesInput,
            coroutine=tools_instance.list_files
        ),
        
        StructuredTool(
            name="get_project_overview",
            description=(
                "Get compressed project context and architecture overview from Knowledge Base. "
                "Returns high-level summary of: architecture, tech stack, key files, patterns.\n"
                "\n**When to use:**\n"
                "- Starting work on a follow-up (understand existing project)\n"
                "- Need architecture context for integration\n"
                "- Understanding project conventions and patterns\n"
                "\n**This is CRITICAL for follow-ups** to maintain consistency with existing code."
            ),
            func=tools_instance.get_project_context,
            args_schema=GetProjectContextInput,
            coroutine=tools_instance.get_project_context
        ),
    ]
    
    logger.info("langchain_tools_created", tool_count=len(tools))
    return tools


# ============================================================================
# TOOL USAGE EXAMPLES (For Agent Prompts)
# ============================================================================

TOOL_USAGE_EXAMPLES = """
# LangChain Tools Usage Examples

## Scenario 1: Follow-Up Modification
**User Request**: "Add dark mode to my todo app"

**Your workflow:**
1. `get_project_overview(project_id=...)` - Understand existing architecture
2. `list_project_files(project_id=..., glob_pattern="*.tsx")` - See component structure
3. `read_project_files(file_paths=["frontend/app/layout.tsx", "frontend/app/globals.css"])` - Read key files
4. `search_codebase(query="theme|Theme", project_id=...)` - Check if theme support exists
5. **Generate code** with context of existing structure

## Scenario 2: Bug Fix
**User Request**: "Fix the error in the login form"

**Your workflow:**
1. `search_codebase(query="login|Login", project_id=...)` - Find login-related files
2. `read_project_files(file_paths=["frontend/components/LoginForm.tsx"])` - Read the form
3. `search_codebase(query="useState|useForm", file_paths=["frontend/components/LoginForm.tsx"])` - Check state management
4. **Generate fix** based on current implementation

## Best Practices

1. **Always read before modifying** - Use `read_project_files` to understand current implementation
2. **Search for patterns** - Use `search_codebase` to find how similar features are implemented
3. **Understand structure** - Use `list_project_files` to see organization
4. **Get context** - Use `get_project_overview` for follow-ups
5. **Limit tool calls** - Only use tools when necessary
"""
