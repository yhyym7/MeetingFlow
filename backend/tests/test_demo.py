import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai.adapters import AnalysisError
from app.ai.analysis import analyze_text
from app.ai.demo import DEMO_TEXT, DemoAnalysisAdapter
from app.models import ProcessingJob
from test_analysis import request
from test_auth_people import login
from test_meetings import create_meeting
from test_workflow import worker


def test_demo_only_accepts_explicit_sample():
    with pytest.raises(AnalysisError) as caught:
        asyncio.run(analyze_text(DemoAnalysisAdapter(), request()))
    assert caught.value.code == "DEMO_SAMPLE_REQUIRED"


def test_demo_sample_uses_real_publication_and_leaves_missing_owner_pending(client, db):
    login(client)
    config = client.get('/api/analysis-config').json()
    assert config['mode'] == 'demo' and config['demo_text'] == DEMO_TEXT
    assert config['audio_max_mb'] == 50 and config['transcription_available'] is False
    meeting = create_meeting(client, db)
    result = client.post(f"/api/meetings/{meeting['id']}/inputs", json={'request_id': str(uuid4()), 'text': DEMO_TEXT}).json()
    asyncio.run(worker(db, DemoAnalysisAdapter()).run_next())
    assert db.get(ProcessingJob, result['job_id']).status == 'SUCCEEDED'
    analysis = client.get(f"/api/meetings/{meeting['id']}/analysis").json()
    assert analysis['mode'] == 'demo'
    rows = client.get(f"/api/meetings/{meeting['id']}/candidates").json()['items']
    assert [row['status'] for row in rows] == ['PUBLISHED', 'NEEDS_INFO', 'DISCUSSION']
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()['total'] == 1
    login(client, 'zhangsan')
    assert client.get('/api/analysis-config').json()['demo_text'] is None


def test_non_sample_text_fails_with_specific_code_without_tasks(client, db):
    login(client)
    meeting = create_meeting(client, db)
    result = client.post(f"/api/meetings/{meeting['id']}/inputs", json={'request_id': str(uuid4()), 'text': '普通真实会议文本'}).json()
    asyncio.run(worker(db, DemoAnalysisAdapter()).run_next())
    assert client.get(f"/api/jobs/{result['job_id']}").json()['error_code'] == 'DEMO_SAMPLE_REQUIRED'
    assert client.get(f"/api/meetings/{meeting['id']}/tasks").json()['total'] == 0
