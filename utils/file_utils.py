"""
File Utilities
Helper functions for file operations
"""
import hashlib
import structlog
from typing import Literal

logger = structlog.get_logger(__name__)

# Language detection mapping
EXTENSION_TO_LANGUAGE = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".py": "python",
    ".json": "json",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".md": "markdown",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sh": "bash",
    ".env": "env",
    ".txt": "text",
}


def calculate_file_hash(content: str) -> str:
    """
    Calculate SHA256 hash of file content.
    
    Args:
        content: File content string
        
    Returns:
        str: SHA256 hash (hex)
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def detect_language(file_path: str) -> str:
    """
    Detect programming language from file extension.
    
    Args:
        file_path: Path to file
        
    Returns:
        str: Language identifier
    """
    # Get extension
    extension = None
    if "." in file_path:
        extension = "." + file_path.split(".")[-1]
    
    # Map to language
    language = EXTENSION_TO_LANGUAGE.get(extension, "text")
    
    return language


def count_lines(content: str) -> int:
    """
    Count lines in file content.
    
    Args:
        content: File content string
        
    Returns:
        int: Number of lines
    """
    if not content:
        return 0
    return len(content.split("\n"))


def estimate_tokens(content: str) -> int:
    """
    Rough estimation of tokens from character count.
    Uses approximation: 1 token ≈ 4 characters
    
    Args:
        content: Content string
        
    Returns:
        int: Estimated token count
    """
    return len(content) // 4
