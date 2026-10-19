"""LLM helper utilities: robust JSON extraction from model text. Model access lives in app.core.llm_gateway."""
import re
import json
from typing import Optional, Dict, Any


def extract_json_from_text(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Robustly extract a JSON object from LLM response text.
    Handles pure JSON, markdown fenced blocks, and leading/trailing prose.
    """
    if not raw_text:
        return None

    cleaned = raw_text.strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    fenced_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
    if fenced_match:
        try:
            return json.loads(fenced_match.group(1).strip())
        except Exception:
            pass

    brace_match = re.search(r"(\{[\s\S]*\})", cleaned)
    if brace_match:
        try:
            return json.loads(brace_match.group(1).strip())
        except Exception:
            pass

    return None
