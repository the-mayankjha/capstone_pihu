import pytest
from python.mcp.client import MCPClient
from python.intelligence.intent import IntentResult
from python.intelligence.planner import Planner


def test_mcp_time_and_date():
    client = MCPClient()

    time_res = client.execute_tool("get_time", {})
    assert time_res.success
    assert "time" in time_res.data
    assert len(time_res.message) > 0

    date_res = client.execute_tool("get_date", {})
    assert date_res.success
    assert "date" in date_res.data
    assert len(date_res.message) > 0


def test_planner_dispatch():
    client = MCPClient()
    planner = Planner(client)

    time_intent = IntentResult("GET_TIME")
    plan = planner.plan(time_intent)
    assert plan.plan_type == "tool_execution"
    assert plan.tool_name == "get_time"

    identity_intent = IntentResult("IDENTITY")
    plan2 = planner.plan(identity_intent)
    assert plan2.plan_type == "direct_response"
    assert "PIHU" in plan2.direct_speech
