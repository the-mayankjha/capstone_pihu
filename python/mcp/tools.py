"""
Built-in MCP tools for PIHU system and web capabilities.
"""

import sys
import webbrowser
import datetime
import subprocess
import urllib.parse
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger("PIHU.MCP")


class MCPResult:
    def __init__(self, success: bool, data: Any, message: str = ""):
        self.success = success
        self.data = data
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
        }


class MCPTool(ABC):
    """Abstract MCP Tool."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        pass


class GetTimeTool(MCPTool):
    name = "get_time"
    description = "Get current local time"

    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        now = datetime.datetime.now()
        # Formatted nicely: "7:15 PM"
        time_str = now.strftime("%I:%M %p").lstrip("0")
        return MCPResult(True, {"time": time_str}, f"It is {time_str}.")


class GetDateTool(MCPTool):
    name = "get_date"
    description = "Get current date"

    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        return MCPResult(True, {"date": date_str}, f"Today is {date_str}.")


class OpenUrlTool(MCPTool):
    name = "open_url"
    description = "Open a URL in default web browser"

    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        url = arguments.get("url", "")
        if not url:
            return MCPResult(False, None, "No URL specified.")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        try:
            webbrowser.open(url)
            target_name = arguments.get("target_name") or url
            return MCPResult(True, {"url": url}, f"Opening {target_name}.")
        except Exception as e:
            logger.error(f"Failed to open URL {url}: {e}")
            return MCPResult(False, None, f"Failed to open URL: {e}")


class OpenAppTool(MCPTool):
    name = "open_application"
    description = "Launch an application on the operating system"

    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        app = arguments.get("app", "").lower()
        if not app:
            return MCPResult(False, None, "No application specified.")

        app_map = {
            "browser": "Google Chrome" if sys.platform == "darwin" else "browser",
            "chrome": "Google Chrome",
            "safari": "Safari",
            "terminal": "Terminal",
            "finder": "Finder",
            "calculator": "Calculator",
            "notes": "Notes",
            "spotify": "Spotify",
            "vs code": "Visual Studio Code",
            "code": "Visual Studio Code",
        }

        target_app = app_map.get(app, app.title())

        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", target_app])
                return MCPResult(True, {"app": target_app}, f"Opening {target_app}.")
            except Exception as e:
                logger.error(f"Failed to open application {target_app}: {e}")
                return MCPResult(False, None, f"Could not launch {target_app}.")
        else:
            return MCPResult(False, None, "Application launching only supported on macOS for now.")


class WebSearchTool(MCPTool):
    name = "web_search"
    description = "Perform a web search"

    def execute(self, arguments: Dict[str, Any]) -> MCPResult:
        query = arguments.get("query", "")
        if not query:
            return MCPResult(False, None, "No search query provided.")

        encoded = urllib.parse.quote(query)
        search_url = f"https://www.google.com/search?q={encoded}"
        try:
            webbrowser.open(search_url)
            return MCPResult(True, {"query": query, "url": search_url}, f"Searching for {query}.")
        except Exception as e:
            logger.error(f"Failed to perform search: {e}")
            return MCPResult(False, None, f"Failed to search: {e}")
