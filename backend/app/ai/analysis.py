import asyncio

from pydantic import ValidationError

from app.ai.adapters import AnalysisAdapter, AnalysisError
from app.ai.contracts import ActionCandidate, AnalysisEnvelope, AnalysisRequest, AnalysisResult, ParsedCandidate


async def analyze_text(adapter: AnalysisAdapter, request: AnalysisRequest, *, timeout_seconds: float = 60) -> AnalysisResult:
    try:
        async with asyncio.timeout(timeout_seconds):
            raw = await adapter.analyze(request)
            repaired = False
            for attempt in range(2):
                try:
                    if not isinstance(raw, str) or len(raw) > 250000:
                        raise AnalysisError("ANALYSIS_OUTPUT_TOO_LARGE_OR_INVALID")
                    envelope = AnalysisEnvelope.model_validate_json(raw)
                    break
                except ValidationError:
                    if attempt == 1:
                        raise AnalysisError("ANALYSIS_INVALID_STRUCTURE") from None
                    raw = await adapter.repair(request, raw, "请返回包含 summary、decisions、risks、actions 的合法 JSON 对象。")
                    repaired = True
            candidates = []
            for index, item in enumerate(envelope.actions):
                try:
                    candidates.append(ParsedCandidate(index=index, raw=item, value=ActionCandidate.model_validate(item)))
                except ValidationError:
                    candidates.append(ParsedCandidate(index=index, raw=item, error="候选结构不完整或包含不允许的字段"))
            return AnalysisResult(mode=adapter.mode, summary=envelope.summary, decisions=envelope.decisions,
                                  risks=envelope.risks, candidates=candidates, raw_output=raw, repaired=repaired)
    except AnalysisError:
        raise
    except TimeoutError:
        raise AnalysisError("ANALYSIS_TIMEOUT", retryable=True) from None
    except Exception:
        # Provider tracebacks may embed headers, URLs or full response bodies.
        raise AnalysisError("ANALYSIS_PROVIDER_ERROR", retryable=True) from None
