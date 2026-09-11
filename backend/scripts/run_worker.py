"""T10 analysis-only worker. Full publication and automatic enqueue arrive in T11/T12."""
import asyncio

from app.ai.workflow import AnalysisWorker


if __name__ == "__main__":
    asyncio.run(AnalysisWorker().run_forever())
