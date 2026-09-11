"""A real LangGraph read-only workflow with explicit demo intent routing, not an LLM."""
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context
from sqlalchemy.orm import Session

from app.models import User
from app.permissions import require_known_user
from app.schemas.assistant import AssistantAnswer
from app.services import assistant_tools


class QueryState(TypedDict, total=False):
    question: str
    action: str
    keyword: str
    result: AssistantAnswer
    trace: list[str]


HELP = "当前为演示查询助手，支持：查看我的任务、查看逾期任务、查看近期会议、统计任务进度，或输入“查找会议：关键词”。结果读取真实授权数据；不支持自由模型问答或修改数据。"


async def answer_query(db: Session, actor: User, question: str) -> AssistantAnswer:
    require_known_user(actor)
    from app.config import get_settings
    direct = question.strip() in {'查看我的任务', '查看逾期任务', '查看近期会议', '统计任务进度'} or question.strip().startswith(('查找会议：', '查找会议:', '语义检索：', '语义检索:'))
    if get_settings().analysis_mode == 'deepseek' and not direct:
        from app.ai.assistant_live import answer_live
        return await answer_live(db, actor, question)

    def classify(state):
        text = state["question"].strip()
        choices = {"查看我的任务": "tasks", "查看逾期任务": "overdue", "查看近期会议": "meetings", "统计任务进度": "statistics"}
        action = choices.get(text, "help")
        keyword = ""
        for prefix in ("查找会议：", "查找会议:"):
            if text.startswith(prefix):
                keyword = text[len(prefix):].strip()
                action = "search" if 1 <= len(keyword) <= 100 else "help"
        for prefix in ('语义检索：', '语义检索:'):
            if text.startswith(prefix):
                keyword = text[len(prefix):].strip()
                action = 'semantic' if 1 <= len(keyword) <= 100 else 'help'
        return {"action": action, "keyword": keyword, "trace": ["CLASSIFY_DEMO"]}

    def query(state):
        action = state["action"]
        if action == "tasks":
            result = assistant_tools.query_tasks(db, actor)
        elif action == "overdue":
            result = assistant_tools.query_tasks(db, actor, overdue=True)
        elif action == "meetings":
            result = assistant_tools.query_meetings(db, actor)
        elif action == "statistics":
            result = assistant_tools.query_statistics(db, actor)
        elif action == 'semantic':
            if get_settings().embedding_mode == 'local':
                from app.services.semantic_search import search_semantic
                result = search_semantic(db, actor, state['keyword'])
            else:
                result = assistant_tools.search_meetings(db, actor, state['keyword'])
        else:
            result = assistant_tools.search_meetings(db, actor, state["keyword"])
        return {"result": result, "trace": [*state["trace"], f"TOOL_{action.upper()}"]}

    def help_node(state):
        return {"result": AssistantAnswer(answer=HELP), "trace": [*state["trace"], "HELP_WITHOUT_TOOL"]}

    def finish(state):
        result = state["result"]
        if get_settings().analysis_mode == 'deepseek':
            result.mode = 'deepseek'
        result.trace = [*state["trace"], "RESPOND"]
        return {"result": result}

    graph = StateGraph(QueryState)
    graph.add_node("classify", classify)
    graph.add_node("query", query)
    graph.add_node("help", help_node)
    graph.add_node("finish", finish)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges("classify", lambda s: "help" if s["action"] == "help" else "query", {"help": "help", "query": "query"})
    graph.add_edge("query", "finish")
    graph.add_edge("help", "finish")
    graph.add_edge("finish", END)
    # No loop: at most one authorized tool call. No database session or private data is traced externally.
    with tracing_context(enabled=False):
        state = await graph.compile().ainvoke({"question": question}, config={"recursion_limit": 6})
    return state["result"]
