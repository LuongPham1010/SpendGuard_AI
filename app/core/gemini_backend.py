"""Gemini backend for the gateway (google-genai SDK). Imported only by app/core/llm_gateway.py.

Key rotation: when a call fails with a quota or capacity error (429/503), the next configured key is tried
before falling back to the next model. Keys come from GEMINI_API_KEY (primary) and GEMINI_API_KEYS (comma list).
"""
import json
from typing import List, Optional

from app.core.llm_gateway import LLMResult, Part

_ROTATE_MARKERS = ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "quota", "high demand")


def _should_rotate(ex: Exception) -> bool:
    msg = f"{type(ex).__name__} {ex}"
    return any(m in msg for m in _ROTATE_MARKERS)


class GeminiBackend:
    name = "gemini"

    def __init__(self, api_key: str, models: List[str], extra_keys: Optional[List[str]] = None):
        from google import genai
        keys = [k for k in [api_key] + list(extra_keys or []) if k]
        keys = [k for i, k in enumerate(keys) if k not in keys[:i]]
        self.clients = [genai.Client(api_key=k) for k in keys]
        self.models = [m for i, m in enumerate(models) if m not in models[:i]]
        self._preferred = 0          # index of the last key that answered; an exhausted key is not retried first

    def _call(self, client, model: str, contents, config) -> LLMResult:
        from google.genai import types
        resp = client.models.generate_content(model=model, contents=contents, config=types.GenerateContentConfig(**config))
        calls = []
        for cand in resp.candidates or []:
            for part in (cand.content.parts if cand.content else []) or []:
                fc = getattr(part, "function_call", None)
                if fc:
                    calls.append({"name": fc.name, "args": dict(fc.args or {})})
        try:
            text = resp.text or ""
        except Exception:
            text = ""
        data = None
        if text:
            try:
                data = json.loads(text)
            except Exception:
                data = None
        return LLMResult(available=True, text=text, data=data if isinstance(data, dict) else None,
                         function_calls=calls, model=model)

    def complete(self, prompt: str, images: List[Part], schema: Optional[dict], tools: Optional[list]) -> LLMResult:
        from google.genai import types
        contents = [prompt] + [types.Part.from_bytes(data=p.content, mime_type=p.mime_type) for p in images]
        config = {}
        if schema is not None:
            config["response_mime_type"] = "application/json"
        if tools:
            config["tools"] = [types.Tool(function_declarations=tools)]
        last_err: Optional[Exception] = None
        n = len(self.clients)
        for model in self.models:
            for idx in [(self._preferred + i) % n for i in range(n)]:
                try:
                    result = self._call(self.clients[idx], model, contents, config)
                    self._preferred = idx
                    return result
                except Exception as ex:
                    last_err = ex
                    if _should_rotate(ex):
                        continue          # quota/capacity: try the next key for the same model
                    break                 # any other error (404 model, 400 request): try the next model
        return LLMResult(available=False, fallback=True, flags=[f"ALL_MODELS_FAILED: {type(last_err).__name__}"])
