from typing import Protocol

from app.ai.contracts import AnalysisRequest


class AnalysisAdapter(Protocol):
    mode: str

    async def analyze(self, request: AnalysisRequest) -> str: ...

    async def repair(self, request: AnalysisRequest, raw_output: str, issues: str) -> str: ...


class AnalysisError(Exception):
    def __init__(self, code: str, *, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class UnconfiguredAnalysisAdapter:
    mode = "unconfigured"

    async def analyze(self, request: AnalysisRequest) -> str:
        raise AnalysisError("ANALYSIS_NOT_CONFIGURED")

    async def repair(self, request: AnalysisRequest, raw_output: str, issues: str) -> str:
        raise AnalysisError("ANALYSIS_NOT_CONFIGURED")


class FixtureAnalysisAdapter:
    """A deterministic test double, never presented as a real model response."""
    mode = "fixture"

    def __init__(self, output: str, repair_output: str | None = None):
        self.output = output
        self.repair_output = repair_output
        self.analyze_calls = 0
        self.repair_calls = 0

    async def analyze(self, request: AnalysisRequest) -> str:
        self.analyze_calls += 1
        return self.output

    async def repair(self, request: AnalysisRequest, raw_output: str, issues: str) -> str:
        self.repair_calls += 1
        return self.repair_output if self.repair_output is not None else self.output
