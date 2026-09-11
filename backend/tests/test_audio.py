import io
import wave
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import MeetingAudio, MeetingInput, ProcessingJob
from test_auth_people import login
from test_meetings import create_meeting
from test_managers import team


@pytest.fixture
def audio_store(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), 'audio_storage_dir', tmp_path / 'audio')
    monkeypatch.setattr(get_settings(), 'audio_max_mb', 1)
    return tmp_path / 'audio'


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 800)
    return output.getvalue()


def upload(client, meeting_id, data=None, filename='会议录音.wav', request_id=None):
    return client.post(f'/api/meetings/{meeting_id}/audio',
        params={'filename': filename, 'request_id': request_id or str(uuid4())},
        content=wav_bytes() if data is None else data, headers={'Content-Type': 'application/octet-stream'})


def test_audio_upload_idempotence_download_and_no_fake_transcription(client, db, audio_store):
    login(client)
    meeting = create_meeting(client, db)
    text = client.post(f"/api/meetings/{meeting['id']}/inputs", json={'request_id': str(uuid4()), 'text': '已有原文'}).json()
    request_id = str(uuid4())
    first = upload(client, meeting['id'], request_id=request_id)
    assert first.status_code == 201, first.text
    record = first.json()
    assert record['status'] == 'AWAITING_TRANSCRIPTION'
    assert not {'storage_name', 'content_hash', 'created_by_id'} & record.keys()
    again = upload(client, meeting['id'], request_id=request_id)
    assert again.json()['id'] == record['id'] and len(list(audio_store.iterdir())) == 1
    assert upload(client, meeting['id'], data=wav_bytes() + b'changed', request_id=request_id).status_code == 409
    assert len(list(audio_store.iterdir())) == 1
    detail = client.get(f"/api/meetings/{meeting['id']}").json()
    assert detail['current_input']['id'] == text['id'] and detail['current_audio']['id'] == record['id']
    download = client.get(f"/api/meetings/{meeting['id']}/audio/{record['id']}/download")
    assert download.content == wav_bytes() and download.headers['content-type'] == 'audio/wav'
    assert 'attachment' in download.headers['content-disposition']
    assert download.headers['cache-control'] == 'no-store'
    assert client.post(f"/api/meetings/{meeting['id']}/audio/{record['id']}/transcribe").status_code == 503
    assert db.scalar(select(func.count()).select_from(MeetingInput).where(MeetingInput.meeting_id == meeting['id'])) == 1
    assert db.scalar(select(func.count()).select_from(ProcessingJob).where(ProcessingJob.meeting_id == meeting['id'])) == 1
    second = upload(client, meeting['id'], filename='另一段.wav').json()
    assert second['id'] != record['id']
    assert client.get(f"/api/meetings/{meeting['id']}").json()['current_audio']['id'] == second['id']


@pytest.mark.parametrize('username,allowed', [('zhangsan', True), ('wangwu', False), ('zhaoliu', False)])
def test_audio_permissions_follow_meeting_and_revocation(client, db, audio_store, username, allowed):
    login(client)
    meeting = create_meeting(client, db)
    record = upload(client, meeting['id']).json()
    path = f"/api/meetings/{meeting['id']}/audio/{record['id']}"
    login(client, username)
    assert client.get(path + '/download').status_code == (200 if allowed else 404)
    assert upload(client, meeting['id']).status_code == 403
    assert client.post(path + '/transcribe').status_code == 403
    login(client)
    client.patch(f"/api/meetings/{meeting['id']}", json={'participant_ids': []})
    login(client, username)
    assert client.get(path + '/download').status_code == 404


@pytest.mark.parametrize('filename,data,code', [
    ('empty.wav', b'', 422), ('fake.wav', b'not an audio file', 422),
    ('bad.txt', b'text', 422), ('../escape.wav', None, 422), ('C:\\secret.wav', None, 422),
    ('large.wav', b'x' * (1024 * 1024 + 1), 413),
], ids=['empty', 'fake', 'extension', 'relative-path', 'absolute-path', 'too-large'])
def test_invalid_uploads_leave_no_files_or_rows(client, db, audio_store, filename, data, code):
    login(client)
    meeting = create_meeting(client, db)
    assert upload(client, meeting['id'], data=data, filename=filename).status_code == code
    assert not audio_store.exists() or list(audio_store.iterdir()) == []
    assert db.scalar(select(MeetingAudio.id).where(MeetingAudio.meeting_id == meeting['id'])) is None


def test_manager_audio_scope_cross_meeting_ids_and_missing_file(client, db, audio_store, team):
    from test_managers import login as manager_login, meeting as manager_meeting
    manager_login(client, 'boss')
    boss_meeting = manager_meeting(client, departments=[team['manager'].department_id])
    record = upload(client, boss_meeting['id']).json()
    manager_login(client, team['manager'])
    route = f"/api/meetings/{boss_meeting['id']}/audio/{record['id']}/download"
    assert client.get(route).status_code == 200
    assert upload(client, boss_meeting['id']).status_code == 403
    own = manager_meeting(client)
    assert upload(client, own['id']).status_code == 201
    assert client.get(f"/api/meetings/{own['id']}/audio/{record['id']}/download").status_code == 404
    stored = db.get(MeetingAudio, record['id'])
    (audio_store / stored.storage_name).unlink()
    assert client.get(route).status_code == 404


def test_stream_size_limit_without_content_length(client, db, audio_store):
    login(client)
    meeting = create_meeting(client, db)
    response = client.post(f"/api/meetings/{meeting['id']}/audio",
        params={'filename': 'stream.wav', 'request_id': str(uuid4())},
        content=iter([wav_bytes(), b'\0' * (1024 * 1024)]),
        headers={'Content-Type': 'application/octet-stream'})
    assert response.status_code == 413
    assert list(audio_store.iterdir()) == []
    assert db.scalar(select(MeetingAudio.id).where(MeetingAudio.meeting_id == meeting['id'])) is None
