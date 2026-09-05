import pytest
from python.intelligence.intent import IntentEngine


def test_intent_classification():
    engine = IntentEngine()

    # Time intents
    res = engine.classify("What time is it?")
    assert res.intent == "GET_TIME"

    res = engine.classify("tell me the time")
    assert res.intent == "GET_TIME"

    # Date intents
    res = engine.classify("What is today's date?")
    assert res.intent == "GET_DATE"

    # URL intents
    res = engine.classify("Open GitHub")
    assert res.intent == "OPEN_URL"
    assert "github.com" in res.parameters.get("url", "")

    res = engine.classify("go to https://example.com")
    assert res.intent == "OPEN_URL"
    assert res.parameters.get("url") == "https://example.com"

    # App intents
    res = engine.classify("Open Chrome")
    assert res.intent == "OPEN_APPLICATION"
    assert res.parameters.get("app") == "chrome"

    # Search intents
    res = engine.classify("Search for Rust Tauri tutorials")
    assert res.intent == "SEARCH_WEB"
    assert res.parameters.get("query") == "rust tauri tutorials"

    # Identity
    res = engine.classify("Who are you?")
    assert res.intent == "IDENTITY"
