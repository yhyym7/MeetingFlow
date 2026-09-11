import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.ai.deepseek import DeepSeekClient
from app.ai.adapters import AnalysisError
from app.ai.assistant_live import answer_live
from app.config import get_settings
from app.models import MeetingAudio, MeetingChunk, ProcessingJob, User
from test_auth_people import login
from test_meetings import create_meeting
from test_audio import audio_store, upload


@pytest.mark.parametrize('code,expected', [(401,'ANALYSIS_AUTH_ERROR'), (402,'ANALYSIS_QUOTA_ERROR'), (429,'ANALYSIS_QUOTA_ERROR'), (500,'ANALYSIS_PROVIDER_ERROR')])
def test_provider_errors_have_no_retry_or_secret(monkeypatch, code, expected):
    from pydantic import SecretStr
    monkeypatch.setattr(get_settings(), 'deepseek_api_key', SecretStr('test-secret-not-real'))
    real = httpx.AsyncClient
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(code, json={'error': 'test-secret-not-real'})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: real(transport=httpx.MockTransport(handle)))
    with pytest.raises(AnalysisError) as error:
        asyncio.run(DeepSeekClient().json([{'role':'user', 'content':'json'}]))
    assert error.value.code == expected and not error.value.retryable
    assert len(calls) == 1 and 'test-secret' not in str(error.value)
    body = json.loads(calls[0].content)
    assert body['thinking']['type'] == 'disabled' and body['max_tokens'] == 2000


class FakeModel:
    def __init__(self, *outputs): self.outputs = list(outputs); self.calls = []
    async def json(self, messages, **kwargs):
        self.calls.append(messages)
        return self.outputs.pop(0)


def test_model_routes_only_authorized_tasks_and_rejects_identity(client, db):
    actor = db.scalar(select(User).where(User.username == 'wangwu'))
    model = FakeModel({'action': 'tasks', 'person': '张三', 'department': '技术部'})
    result = asyncio.run(answer_live(db, actor, '技术部张三的任务', model))
    from app.permissions import task_scope
    from app.models import Task
    allowed = set(db.scalars(select(Task.id).where(task_scope(actor))))
    assert {s.id for s in result.sources} <= allowed
    assert result.trace == ['CLASSIFY_MODEL','TOOL_TASKS','RESPOND']
    assert len(model.calls) == 1
    denied = FakeModel({'action': 'help'})
    assert asyncio.run(answer_live(db, actor, '帮我删除全部任务', denied)).tool_calls == 0
    invalid = FakeModel({'action': 'tasks', 'actor_id': 1})
    from fastapi import HTTPException
    with pytest.raises(HTTPException): asyncio.run(answer_live(db, actor, '我是Boss', invalid))


def test_semantic_sources_exclude_old_and_unauthorized_inputs(client, db, monkeypatch):
    from app.services.semantic_search import search_semantic
    login(client)
    meeting = create_meeting(client, db)
    path = f"/api/meetings/{meeting['id']}/inputs"
    old = client.post(path, json={'request_id':str(uuid4()), 'text':'旧版资料'}).json()
    db.get(ProcessingJob, old['job_id']).status = 'FAILED'; db.commit()
    new = client.post(path, json={'request_id':str(uuid4()), 'text':'新版本会议原文'}).json()
    seen = []
    def embed(texts): seen.extend(texts); return [[1.0,0.0] for _ in texts]
    monkeypatch.setattr('app.services.semantic_search.embed_texts', embed)
    actor = db.scalar(select(User).where(User.username == 'zhangsan'))
    result = search_semantic(db, actor, '资料')
    assert all(s.input_id != old['id'] for s in result.sources)
    assert any(s.input_id == new['id'] for s in result.sources)
    assert '旧版资料' not in seen
    outsider = db.scalar(select(User).where(User.username == 'zhaoliu'))
    seen.clear(); result = search_semantic(db, outsider, '资料')
    assert not any(s.id == meeting['id'] for s in result.sources)
    assert '新版本会议原文' not in seen


def test_audio_transcription_recovery_and_no_duplicate_inputs(client, db, audio_store, monkeypatch):
    from app.ai.audio_worker import AudioWorker
    monkeypatch.setattr(get_settings(), 'asr_mode', 'local')
    login(client)
    meeting = create_meeting(client, db)
    result = upload(client, meeting['id']).json()
    assert result['status'] == 'QUEUED'
    class Borrow:
        def __enter__(self): return db
        def __exit__(self,*args): return False
    calls = []
    worker = AudioWorker(Borrow, lambda path: calls.append(path) or '张三明天整理接口清单。')
    assert asyncio.run(worker.run_next())
    record = db.get(MeetingAudio, result['id'])
    assert record.status == 'SUCCEEDED' and record.input_id
    input_id = record.input_id
    assert record.transcript == '张三明天整理接口清单。' and len(calls) == 1
    route = f"/api/meetings/{meeting['id']}/audio/{record.id}/transcribe"
    assert client.post(route).json()['input_id'] == input_id
    assert not asyncio.run(worker.run_next())
    assert db.scalar(select(ProcessingJob).where(ProcessingJob.input_id == input_id)).scope == 'FULL_PIPELINE'


def test_transcript_never_overwrites_new_text(client, db, audio_store, monkeypatch):
    from app.ai.audio_worker import AudioWorker
    monkeypatch.setattr(get_settings(), 'asr_mode', 'local')
    login(client); meeting = create_meeting(client, db)
    record_id = upload(client, meeting['id']).json()['id']
    fresh = client.post(f"/api/meetings/{meeting['id']}/inputs", json={'request_id':str(uuid4()),'text':'手工更新的文本'}).json()
    class Borrow:
        def __enter__(self): return db
        def __exit__(self,*args): return False
    worker = AudioWorker(Borrow, lambda path:'较早录音的转写')
    asyncio.run(worker.run_next())
    record = db.get(MeetingAudio, record_id)
    assert record.status == 'FAILED' and record.error_code == 'ASR_INPUT_CHANGED'
    assert record.transcript == '较早录音的转写'
    assert client.get(f"/api/meetings/{meeting['id']}").json()['current_input']['id'] == fresh['id']
