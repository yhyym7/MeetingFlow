from sqlalchemy import select

from app.ai.local_models import EMBEDDING_ID, embed_texts
from app.models import Meeting, MeetingChunk, MeetingInput
from app.permissions import meeting_scope, require_known_user
from app.schemas.assistant import AssistantAnswer, Source
from app.services.candidates import current_input_condition
from app.services.assistant_tools import search_meetings


def search_semantic(db, actor, question):
    require_known_user(actor)
    # Only authorized, latest-version text is loaded, even for local inference.
    rows = db.execute(select(Meeting.id, Meeting.title, MeetingInput.id, MeetingInput.version, MeetingChunk)
        .select_from(Meeting).join(MeetingInput, MeetingInput.meeting_id == Meeting.id)
        .join(MeetingChunk, MeetingChunk.input_id == MeetingInput.id)
        .where(meeting_scope(actor), current_input_condition())
        .order_by(Meeting.starts_at.desc(), Meeting.id.desc(), MeetingChunk.position).limit(1000)).all()
    if not rows:
        return AssistantAnswer(answer='当前授权范围内没有可检索的会议原文。', search_mode='semantic', tool_calls=1)
    try:
        pending = [row[-1] for row in rows if row[-1].embedding_model != EMBEDDING_ID or not row[-1].embedding]
        vectors = embed_texts([chunk.text for chunk in pending] + [question])
        for chunk, vector in zip(pending, vectors[:-1]):
            chunk.embedding, chunk.embedding_model = vector, EMBEDDING_ID
        db.flush()
        query = vectors[-1]
        scored = [(sum(a * b for a, b in zip(row[-1].embedding, query)), row) for row in rows]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        selected = [row for score, row in scored[:5] if score >= 0.45]
        sources = [Source(kind='meeting', id=mid, title=title, input_id=iid, input_version=version,
                          chunk_id=chunk.id, excerpt=chunk.text, start_offset=chunk.start_offset,
                          end_offset=chunk.end_offset) for mid, title, iid, version, chunk in selected]
        db.commit()
        return AssistantAnswer(answer=f'找到 {len(sources)} 个可能相关的授权会议片段。' if sources else '没有找到足够相关的会议片段。',
                               sources=sources, search_mode='semantic', tool_calls=1)
    except Exception:
        db.rollback()
        result = search_meetings(db, actor, question[:100])
        result.answer = '本地语义检索暂不可用，已改用关键词检索。' + result.answer
        return result
