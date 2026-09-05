"""
Action Planner for translating intents into execution plans.
"""

import logging
from typing import Dict, Any, Optional
from .intent import IntentResult
from python.mcp.client import MCPClient

logger = logging.getLogger("PIHU.PLANNER")


class ActionPlan:
    def __init__(self, plan_type: str, tool_name: Optional[str] = None, arguments: Optional[Dict[str, Any]] = None, direct_speech: Optional[str] = None):
        self.plan_type = plan_type  # "tool_execution" | "direct_response"
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.direct_speech = direct_speech

    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_type": self.plan_type,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "direct_speech": self.direct_speech,
        }


class Planner:
    """Plans the next action based on detected intent."""

    def __init__(self, mcp_client: MCPClient):
        self.mcp_client = mcp_client

    def plan(self, intent_result: IntentResult) -> ActionPlan:
        intent = intent_result.intent
        params = intent_result.parameters
        logger.info(f"Planning for intent: '{intent}' with params {params}")

        if intent == "GET_TIME":
            return ActionPlan("tool_execution", tool_name="get_time", arguments={})

        elif intent == "GET_DATE":
            return ActionPlan("tool_execution", tool_name="get_date", arguments={})

        elif intent == "OPEN_URL":
            return ActionPlan("tool_execution", tool_name="open_url", arguments=params)

        elif intent == "OPEN_APPLICATION":
            return ActionPlan("tool_execution", tool_name="open_application", arguments=params)

        elif intent == "SEARCH_WEB":
            return ActionPlan("tool_execution", tool_name="web_search", arguments=params)

        elif intent == "IDENTITY":
            return ActionPlan(
                "direct_response",
                direct_speech="I am PIHU, your desktop AI interaction layer. I am here to help you navigate and interact seamlessly.",
            )

        elif intent == "GREETING":
            return ActionPlan("direct_response", direct_speech="Hello! How can I help you?")

        else:
            raw = params.get("raw_text", "")
            return ActionPlan("direct_response", direct_speech=f"I heard: {raw}. How would you like me to assist?")
