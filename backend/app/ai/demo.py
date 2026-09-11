"""Explicit, fixed demonstration data. This adapter does not analyze arbitrary text."""
import json

from app.ai.adapters import AnalysisError, FixtureAnalysisAdapter

DEMO_TEXT = "张三明天整理接口清单，王五协助核对字段。\n需要有人整理测试用例，暂未确定负责人。\n可以考虑下次增加自动化测试，目前先讨论。"


class DemoAnalysisAdapter(FixtureAnalysisAdapter):
    mode = "demo"

    def __init__(self):
        super().__init__(json.dumps({
            "summary": "演示会议确定整理接口清单；测试用例整理尚待指定负责人。",
            "decisions": ["先整理并核对接口清单"],
            "risks": ["测试用例整理尚未指定负责人", "自动化测试仅作讨论，暂不派发"],
            "actions": [
                {"title": "整理接口清单", "kind": "COMMITTED", "owner": {"name": "张三", "department": "技术部"},
                 "collaborators": [{"name": "王五", "department": "产品部"}], "deadline_text": "明天",
                 "source_quote": "张三明天整理接口清单，王五协助核对字段。"},
                {"title": "整理测试用例", "kind": "COMMITTED", "owner": None,
                 "source_quote": "需要有人整理测试用例，暂未确定负责人。"},
                {"title": "考虑增加自动化测试", "kind": "DISCUSSION", "owner": None,
                 "source_quote": "可以考虑下次增加自动化测试，目前先讨论。"},
            ],
        }, ensure_ascii=False))

    async def analyze(self, request):
        if request.text.strip() != DEMO_TEXT:
            raise AnalysisError("DEMO_SAMPLE_REQUIRED")
        return await super().analyze(request)
