"""
Intent Engine for classifying transcribed user utterances into structured intents.
"""

import re
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("PIHU.INTENT")


class IntentResult:
    def __init__(self, intent: str, confidence: float = 1.0, parameters: Optional[Dict[str, Any]] = None):
        self.intent = intent
        self.confidence = confidence
        self.parameters = parameters or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "parameters": self.parameters,
        }


class IntentEngine:
    """Lightweight rule-based and pattern matching intent classifier for MVP."""

    def __init__(self):
        pass

    def classify(self, text: str) -> IntentResult:
        """Classify user text into an intent."""
        cleaned = text.strip().lower()
        # Strip trailing punctuation
        cleaned = re.sub(r"[?!.,]+$", "", cleaned).strip()
        logger.info(f"Classifying intent for: '{cleaned}'")

        if not cleaned:
            return IntentResult("UNKNOWN", 0.0)

        # 1. Time
        if re.search(r"\b(what time is it|what's the time|tell me the time|current time|the time)\b", cleaned):
            return IntentResult("GET_TIME", 0.95)

        # 2. Date
        if re.search(r"\b(what date is it|what's today's date|what is today's date|tell me today's date|what day is it|today's date)\b", cleaned):
            return IntentResult("GET_DATE", 0.95)

        # 3. Open URL
        open_url_match = re.search(r"\b(?:open|go to|launch)\s+(https?://\S+|github|google|youtube|reddit|twitter|x\.com|wikipedia)(?:\.com|\.org|\.io)?\b", cleaned)
        if open_url_match:
            target = open_url_match.group(1).strip()
            if not target.startswith("http"):
                target_url = f"https://{target}.com" if not target.endswith((".com", ".org", ".io")) else f"https://{target}"
            else:
                target_url = target
            return IntentResult("OPEN_URL", 0.95, {"url": target_url, "target_name": target})

        # 4. Open Application
        open_app_match = re.search(r"\b(?:open|launch)\s+(?:my\s+)?(browser|chrome|safari|terminal|finder|calculator|spotify|code|vs code|notes|settings)\b", cleaned)
        if open_app_match:
            app_name = open_app_match.group(1).strip()
            return IntentResult("OPEN_APPLICATION", 0.95, {"app": app_name})

        # 5. Web Search
        search_match = re.search(r"\b(?:search for|search the web for|search|google)\s+(.+)$", cleaned)
        if search_match:
            query = search_match.group(1).strip()
            return IntentResult("SEARCH_WEB", 0.90, {"query": query})

        # 6. General Greeting / Identity
        if re.search(r"\b(who are you|what are you|what can you do|what is pihu)\b", cleaned):
            return IntentResult("IDENTITY", 0.90)

        if re.search(r"^(hello|hi|hey pihu|hey|hi pihu)$", cleaned):
            return IntentResult("GREETING", 0.90)

        # Default fallback
        return IntentResult("GENERAL_QUERY", 0.5, {"raw_text": text})
