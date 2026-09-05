"""
MCP Client for managing and executing tools.
"""

import logging
from typing import Dict, Any, Optional
from .tools import MCPTool, MCPResult, GetTimeTool, GetDateTool, OpenUrlTool, OpenAppTool, WebSearchTool

logger = logging.getLogger("PIHU.MCP")


class MCPClient:
    """Client for registering and invoking MCP capability tools."""

    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        for tool_cls in [GetTimeTool, GetDateTool, OpenUrlTool, OpenAppTool, WebSearchTool]:
            tool = tool_cls()
            self._tools[tool.name] = tool
        logger.info(f"Registered {len(self._tools)} default MCP tools: {list(self._tools.keys())}")

    def register_tool(self, tool: MCPTool):
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[MCPTool]:
        return self._tools.get(name)

    def execute_tool(self, name: str, arguments: Dict[str, Any]) -> MCPResult:
        tool = self.get_tool(name)
        if not tool:
            logger.error(f"MCP tool '{name}' not found.")
            return MCPResult(False, None, f"Tool '{name}' is not available.")

        logger.info(f"Executing MCP tool '{name}' with arguments: {arguments}")
        try:
            result = tool.execute(arguments)
            logger.info(f"MCP tool '{name}' completed. Success: {result.success}, Message: {result.message}")
            return result
        except Exception as e:
            logger.error(f"Error executing MCP tool '{name}': {e}")
            return MCPResult(False, None, f"Execution failed: {e}")
