"""
Temporary Debug Logger for Qbit Backend
----------------------------------------
Human-readable logging for major component events.
SAFE TO DELETE - no codebase impact if removed.

Usage:
    from utils.debug_logger import dlog
    dlog("Central Hub", "SCP generated for portfolio project")
    dlog("FullStack Agent", "Generated 15 files", error=False)
    dlog("E2B", "npm install failed in /frontend", error=True)
"""
import os
import sys
from datetime import datetime
from pathlib import Path

# Log file location (temp directory)
LOG_FILE = Path(os.environ.get("TEMP", "/tmp")) / "qbit_debug.log"

# ANSI colors for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

# Component mappings for shorter logs
COMPONENT_MAP = {
    "central hub": "Hub",
    "fullstack agent": "Agent",
    "e2b": "E2B",
    "websocket": "WS",
    "database": "DB",
}


def format_component(component: str) -> str:
    """Format component name to short bracketed style."""
    key = component.lower()
    short_name = COMPONENT_MAP.get(key, component)
    return f"[{short_name}]"


def dlog(component: str, message: str, error: bool = False) -> None:
    """
    Log a debug message to temp file and terminal.
    
    Args:
        component: Component name (e.g., "Central Hub", "E2B")
        message: Short human-readable message
        error: True if this is an error message
    """
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        comp_tag = format_component(component)
        
        # Color based on error state
        if error:
            color = RED
            status = "ERROR"
        else:
            color = GREEN
            status = "OK"
        
        # Terminal output (colored)
        # Format: [12:00:00] [Hub] Message
        term_line = f"{color}{BOLD}[{timestamp}]{RESET} {BLUE}{comp_tag}{RESET} {message}"
        if error:
            term_line = f"{RED}{BOLD}[{timestamp}] {comp_tag} ERROR: {message}{RESET}"
        
        print(term_line, file=sys.stderr)
        
        # File output (plain text)
        file_line = f"[{timestamp}] [{status}] {component}: {message}\n"
        
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(file_line)
            
    except Exception:
        # Silent fail - never break the app
        pass


def dlog_start(component: str) -> None:
    """Log component start."""
    dlog(component, "Started", error=False)


def dlog_complete(component: str, details: str = "") -> None:
    """Log component completion."""
    msg = "Complete" + (f" - {details}" if details else "")
    dlog(component, msg, error=False)


def dlog_error(component: str, error_msg: str) -> None:
    """Log component error."""
    dlog(component, error_msg, error=True)


def clear_log() -> None:
    """Clear the debug log file."""
    try:
        if LOG_FILE.exists():
            LOG_FILE.unlink()
    except Exception:
        pass


# Auto-clear on import (fresh log each server restart)
clear_log()
dlog("Debug Logger", f"Logging to {LOG_FILE}")
