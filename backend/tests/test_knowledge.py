from uuid import uuid4

from sqlalchemy import delete, func, select

from app.models import MeetingChunk, MeetingInput, ProcessingJob
from app.services.knowledge import backfill_chunks, split_text
from test_auth_people import login
from test_meetings import create_meeting


def test_chunks_preserve_exact_text_overlap_and_boundary_keyword():
    text = '甲' * 590 + '跨边界检索关键词' + '\n第二段' * 380
    chunks = list(split_text(text))
    assert chunks[0][0] == 0 and chunks[-1][1] == len(text)
    assert all(value == text[start:end] and len(value) <= 600 for start, end, value in chunks)
    assert all(a[1] - b[0] == 100 for a, b in zip(chunks, chunks[1:]))
    assert any('跨边界检索关键词' in chunk for _, _, chunk in chunks)
    assert chunks[0][1] <= 600
    assert any(value.endswith('\n') for _, _, value in chunks[:-1])
    assert list(split_text('')) == []


def test_input_and_chunks_idempotence_versioned_sources_and_backfill(client, db):
    login(client)
    meeting = create_meeting(client, db)
    path = f"/api/meetings/{meeting['id']}/inputs"
    payload = {'request_id': str(uuid4()), 'text': '甲' * 590 + '跨边界独特关键词' + '乙' * 700}
    first = client.post(path, json=payload).json()
    again = client.post(path, json=payload).json()
    assert first['id'] == again['id']
    count = db.scalar(select(func.count()).select_from(MeetingChunk).where(MeetingChunk.input_id == first['id']))
    assert count == len(list(split_text(payload['text'])))
    sources = client.post('/api/assistant/query', json={'question': '查找会议：跨边界独特关键词'}).json()['sources']
    source = sources[0]
    assert source['input_id'] == first['id'] and source['input_version'] == 1
    assert source['excerpt'] == payload['text'][source['start_offset']:source['end_offset']]
    route = f"{path}/{first['id']}/chunks/{source['chunk_id']}"
    assert client.get(route).json() == source
    db.get(ProcessingJob, first['job_id']).status = 'FAILED'; db.commit()
    second = client.post(path, json={'request_id': str(uuid4()), 'text': '新版本唯一查询词'}).json()
    assert client.post('/api/assistant/query', json={'question': '查找会议：跨边界独特关键词'}).json()['sources'] == []
    assert client.get(route).json()['input_version'] == 1
    assert client.get(f"{path}/{second['id']}/chunks/{source['chunk_id']}").status_code == 404
    login(client, 'wangwu')
    assert client.get(route).status_code == 404
    login(client)
    db.execute(delete(MeetingChunk).where(MeetingChunk.input_id == second['id'])); db.commit()
    assert backfill_chunks(db) >= 1
    assert backfill_chunks(db) == 0
    assert db.get(MeetingInput, second['id']).text == '新版本唯一查询词'
    login(client, 'zhangsan')
    assert client.get(route).status_code == 200
    login(client)
    client.patch(f"/api/meetings/{meeting['id']}", json={'participant_ids': []})
    login(client, 'zhangsan')
    assert client.get(route).status_code == 404


def test_keyword_wildcards_are_literal_and_results_capped(client, db):
    login(client)
    meeting = create_meeting(client, db)
    text = ('百分号%与下划线_是原文\n' + '长段' * 300) * 8
    client.post(f"/api/meetings/{meeting['id']}/inputs", json={'request_id': str(uuid4()), 'text': text})
    result = client.post('/api/assistant/query', json={'question': '查找会议：百分号%'}).json()
    assert len(result['sources']) == 5
    assert all('百分号%' in s['excerpt'] for s in result['sources'])
    assert client.post('/api/assistant/query', json={'question': '查找会议：不存在%_'}).json()['sources'] == []
