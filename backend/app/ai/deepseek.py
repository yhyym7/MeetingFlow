"""Official endpoint only; no automatic HTTP retries or private payload logging."""
import json
import logging

import httpx

from app.ai.adapters import AnalysisError
from app.ai.prompts import build_messages
from app.config import get_settings


class DeepSeekClient:
    async def complete(self, messages: list[dict], *, max_tokens: int = 2000) -> str:
        settings = get_settings()
        if not settings.deepseek_api_key:
            raise AnalysisError("ANALYSIS_NOT_CONFIGURED")
        try:
            async with httpx.AsyncClient(timeout=55, trust_env=False) as client:
                response = await client.post("https://api.deepseek.com/chat/completions", headers={
                    "Authorization": "Bearer " + settings.deepseek_api_key.get_secret_value(),
                }, json={"model": settings.deepseek_model, "messages": messages,
                         "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"},
                         "temperature": 0, "max_tokens": max_tokens, "stream": False})
            if response.status_code in (401, 403):
                raise AnalysisError("ANALYSIS_AUTH_ERROR")
            if response.status_code in (402, 429):
                raise AnalysisError("ANALYSIS_QUOTA_ERROR")
            response.raise_for_status()
            payload = response.json()
            usage = payload.get('usage', {})
            logging.getLogger('uvicorn.error').info('DeepSeek model=%s prompt_tokens=%s completion_tokens=%s',
                settings.deepseek_model, usage.get('prompt_tokens'), usage.get('completion_tokens'))
            choice = payload["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AnalysisError("ANALYSIS_OUTPUT_TOO_LARGE_OR_INVALID")
            content = choice["message"]["content"]
            if not isinstance(content, str) or len(content) > 250000:
                raise ValueError("invalid content")
            # Meeting analysis validates the raw content and may repair it once.
            return content
        except AnalysisError:
            raise
        except httpx.TimeoutException:
            raise AnalysisError("ANALYSIS_TIMEOUT") from None
        except Exception:
            raise AnalysisError("ANALYSIS_PROVIDER_ERROR") from None

    async def json(self, messages: list[dict], *, max_tokens: int = 2000) -> dict:
        content = await self.complete(messages, max_tokens=max_tokens)
        try:
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError("expected object")
            return result
        except ValueError:
            # Assistant queries still fail without additional paid repair calls.
            raise AnalysisError("ANALYSIS_PROVIDER_ERROR") from None


class DeepSeekAnalysisAdapter:
    mode = "deepseek"
    def __init__(self, client=None):
        self.client = client or DeepSeekClient()

    async def analyze(self, request):
        # Keep the course demo bounded and its inference cost predictable.
        if len(request.text) > 12000:
            raise AnalysisError("ANALYSIS_INPUT_TOO_LONG")
        return await self.client.complete(build_messages(request), max_tokens=3000)

    async def repair(self, request, raw_output, issues):
        messages = build_messages(request)
        messages += [{"role": "assistant", "content": raw_output}, {"role": "user", "content": issues}]
        return await self.client.complete(messages, max_tokens=3000)
