"""
Patch Utilities
Apply JSON patch operations to code files
"""
import structlog
from typing import Dict, List, Literal

logger = structlog.get_logger(__name__)


class PatchOperation:
    """Single patch operation"""
    
    def __init__(
        self,
        operation_type: Literal["insert_after", "insert_before", "replace"],
        anchor: str,
        content: str
    ):
        self.type = operation_type
        self.anchor = anchor
        self.content = content


def apply_patch(
    original_content: str,
    operations: List[Dict[str, str]]
) -> str:
    """
    Apply patch operations to file content.
    
    Args:
        original_content: Original file content
        operations: List of patch operations
            Each operation has:
            - type: "insert_after" | "insert_before" | "replace"
            - anchor: Text to locate
            - content: New content to insert/replace
            
    Returns:
        str: Patched content
    """
    result = original_content
    
    for op in operations:
        op_type = op.get("type")
        anchor = op.get("anchor", "")
        new_content = op.get("content", "")
        
        if not anchor:
            logger.warning("patch_operation_missing_anchor", operation=op)
            continue
        
        try:
            if op_type == "insert_after":
                result = _insert_after(result, anchor, new_content)
            elif op_type == "insert_before":
                result = _insert_before(result, anchor, new_content)
            elif op_type == "replace":
                result = _replace_content(result, anchor, new_content)
            else:
                logger.warning(
                    "unknown_patch_operation_type",
                    type=op_type
                )
                
        except Exception as e:
            logger.error(
                "patch_operation_failed",
                operation_type=op_type,
                error=str(e)
            )
            # Continue with other operations
            
    return result


def _insert_after(content: str, anchor: str, new_content: str) -> str:
    """Insert content after anchor"""
    if anchor not in content:
        logger.warning("anchor_not_found_insert_after", anchor=anchor[:50])
        return content
    
    index = content.find(anchor) + len(anchor)
    return content[:index] + "\n" + new_content + content[index:]


def _insert_before(content: str, anchor: str, new_content: str) -> str:
    """Insert content before anchor"""
    if anchor not in content:
        logger.warning("anchor_not_found_insert_before", anchor=anchor[:50])
        return content
    
    index = content.find(anchor)
    return content[:index] + new_content + "\n" + content[index:]


def _replace_content(content: str, old_content: str, new_content: str) -> str:
    """Replace old content with new content"""
    if old_content not in content:
        logger.warning("content_not_found_for_replace", old_content=old_content[:50])
        return content
    
    return content.replace(old_content, new_content, 1)  # Replace first occurrence
