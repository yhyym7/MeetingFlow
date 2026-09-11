import asyncio
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai.demo import DemoAnalysisAdapter
from app.ai.resolution import load_directory
from app.ai.workflow import AnalysisWorker
from app.models import Department, Meeting, MeetingInput, Task, TaskCollaborator, User
from app.models.base import utc_now
from app.permissions import meeting_scope, task_scope


@pytest.fixture
def team(client, db):
    people = {u.username: u for u in db.scalars(select(User))}
    prefix = uuid4().hex[:12]
    for name, department in [('manager', people['zhangsan'].department_id), ('other', people['wangwu'].department_id)]:
        person = User(username=f'{name}_{prefix}', name=f'测试{name}', role='MANAGER', department_id=department,
                      password_hash=people['zhangsan'].password_hash, is_active=True)
        db.add(person)
        db.flush()
        people[name] = person
    db.commit()
    return people


def login(client, person):
    name = person if isinstance(person, str) else person.username
    response = client.post('/api/auth/login', json={'username': name, 'password': 'test-password-T03'})
    assert response.status_code == 200, response.text


def meeting(client, participants=(), departments=()):
    response = client.post('/api/meetings', json={'title': '部门权限验证', 'starts_at': '2026-09-10T10:00:00+08:00',
        'participant_ids': list(participants), 'department_ids': list(departments)})
    assert response.status_code == 201, response.text
    return response.json()


def task(client, owner, collaborators=(), meeting_id=None):
    response = client.post('/api/tasks', json={'title': '部门任务', 'owner_id': owner.id,
        'collaborator_ids': [p.id for p in collaborators], 'meeting_id': meeting_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_manager_department_required_and_only_boss_can_assign_role(client, db, team):
    login(client, 'boss')
    payload = {'username': f'm_{uuid4().hex[:12]}', 'name': '经理', 'password': 'test-password-T03', 'role': 'MANAGER'}
    assert client.post('/api/users', json=payload).status_code == 422
    assert client.patch(f'/api/users/{team["manager"].id}', json={'department_id': None}).status_code == 422
    login(client, team['manager'])
    payload['department_id'] = team['manager'].department_id
    assert client.post('/api/users', json=payload).status_code == 403
    assert client.patch(f'/api/users/{team["zhangsan"].id}', json={'role': 'BOSS'}).status_code == 403
    assert client.post('/api/departments', json={'name': '越权部门'}).status_code == 403


def test_department_task_management_and_cross_department_personal_access(client, db, team):
    login(client, 'boss')
    own = task(client, team['zhangsan'], [team['wangwu']])
    outside = task(client, team['wangwu'], [team['zhangsan']])
    personal = task(client, team['wangwu'], [team['manager']])
    login(client, team['manager'])
    assert client.get(f'/api/tasks/{outside["id"]}').status_code == 404
    result = client.get(f'/api/tasks/{own["id"]}').json()
    assert result['can_manage'] and result['can_update_status']
    assert client.patch(f'/api/tasks/{own["id"]}', json={'title': '部长调整'}).status_code == 200
    assert client.patch(f'/api/tasks/{own["id"]}/status', json={'status': 'DONE'}).status_code == 200
    assert client.patch(f'/api/tasks/{own["id"]}', json={'owner_id': team['wangwu'].id}).status_code == 403
    detail = client.get(f'/api/tasks/{personal["id"]}').json()
    assert not detail['can_manage'] and not detail['can_update_status']
    assert client.post(f'/api/tasks/{personal["id"]}/events', json={'body': '个人协作反馈'}).status_code == 201
    assert client.patch(f'/api/tasks/{personal["id"]}/status', json={'status': 'DONE'}).status_code == 403
    assert client.delete(f'/api/tasks/{personal["id"]}').status_code == 403
    assert client.delete(f'/api/tasks/{own["id"]}').status_code == 204
    assert client.get(f'/api/tasks/{own["id"]}').status_code == 404


def test_manager_personal_owner_and_boss_meeting_are_separate(client, db, team):
    login(client, 'boss')
    m = meeting(client, [team['manager'].id])
    t = task(client, team['manager'], meeting_id=m['id'])
    login(client, team['manager'])
    assert not client.get(f'/api/meetings/{m["id"]}').json()['can_manage']
    assert client.patch(f'/api/meetings/{m["id"]}', json={'title': '不得修改'}).status_code == 403
    assert client.post(f'/api/meetings/{m["id"]}/inputs', json={'request_id': str(uuid4()), 'text': '原文'}).status_code == 403
    assert client.get(f'/api/meetings/{m["id"]}/candidates').status_code == 403
    assert client.post('/api/tasks', json={'title': '伪造会议任务', 'owner_id': team['zhangsan'].id, 'meeting_id': m['id']}).status_code == 403
    assert client.patch(f'/api/tasks/{t["id"]}/status', json={'status': 'DONE'}).status_code == 200
    own = meeting(client, [team['zhangsan'].id])
    assert own['can_manage']
    assert task(client, team['zhangsan'], meeting_id=own['id'])['can_manage']
    assert client.post('/api/tasks', json={'title': '越部门', 'owner_id': team['wangwu'].id}).status_code == 403


def test_department_invitation_delegate_and_direct_invites_survive(client, db, team):
    department = team['manager'].department_id
    login(client, 'boss')
    m = meeting(client, [team['lisi'].id], [department])
    assert team['manager'].id in m['participant_ids']
    login(client, team['zhangsan'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 404
    login(client, team['manager'])
    response = client.patch(f'/api/meetings/{m["id"]}/departments/{department}/participants', json={'participant_ids': [team['zhangsan'].id]})
    assert response.status_code == 200, response.text
    assert set(response.json()['participant_ids']) == set(m['participant_ids']) | {team['zhangsan'].id}
    assert {p.id for p in load_directory(db, m['id']) if p.participant} == set(response.json()['participant_ids'])
    assert client.patch(f'/api/meetings/{m["id"]}/departments/{department}/participants', json={'participant_ids': [team['wangwu'].id]}).status_code == 422
    login(client, team['zhangsan'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 200
    assert client.patch(f'/api/meetings/{m["id"]}/departments/{department}/participants', json={'participant_ids': []}).status_code == 403
    login(client, team['manager'])
    assert client.patch(f'/api/meetings/{m["id"]}/departments/{department}/participants', json={'participant_ids': []}).status_code == 200
    login(client, team['lisi'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 200
    login(client, team['zhangsan'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 404


def test_revoked_invitation_and_transfer_remove_department_access(client, db, team):
    department = team['manager'].department_id
    login(client, 'boss')
    m = meeting(client, [], [department])
    login(client, team['manager'])
    url = f'/api/meetings/{m["id"]}/departments/{department}/participants'
    assert client.patch(url, json={'participant_ids': [team['zhangsan'].id]}).status_code == 200
    login(client, 'boss')
    assert client.patch(f'/api/users/{team["zhangsan"].id}', json={'department_id': team['other'].department_id}).status_code == 200
    login(client, team['zhangsan'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 404
    login(client, 'boss')
    assert client.patch(f'/api/meetings/{m["id"]}', json={'department_ids': []}).status_code == 200
    login(client, team['manager'])
    assert client.get(f'/api/meetings/{m["id"]}').status_code == 404
    assert client.patch(url, json={'participant_ids': []}).status_code == 404


def test_manager_department_change_revokes_session_and_changes_task_scope(client, db, team):
    login(client, team['manager'])
    cookie = dict(client.cookies)
    login(client, 'boss')
    t = task(client, team['zhangsan'])
    assert client.patch(f'/api/users/{team["manager"].id}', json={'department_id': team['other'].department_id}).status_code == 200
    client.cookies.clear()
    client.cookies.update(cookie)
    assert client.get('/api/auth/me').status_code == 401
    login(client, team['manager'])
    assert client.get(f'/api/tasks/{t["id"]}').status_code == 404


def test_manager_dashboard_and_assistant_match_authorized_lists(client, db, team):
    login(client, 'boss')
    hidden = meeting(client, [team['zhangsan'].id])
    saved = client.post(f'/api/meetings/{hidden["id"]}/inputs', json={'request_id': str(uuid4()), 'text': '保密部门检索词'})
    assert saved.status_code == 202
    task(client, team['zhangsan'], meeting_id=hidden['id'])
    db.commit()
    assert client.post('/api/assistant/query', json={'question': '查找会议：保密部门检索词'}).json()['sources']
    login(client, team['manager'])
    tasks = client.get('/api/tasks?page_size=100').json()
    dashboard = client.get('/api/dashboard').json()
    assert dashboard['role'] == 'MANAGER'
    assert dashboard['statistics']['total'] == tasks['total']
    result = client.post('/api/assistant/query', json={'question': '查看我的任务'}).json()
    assert {s['id'] for s in result['sources']} <= {t['id'] for t in tasks['items']}
    assert not client.post('/api/assistant/query', json={'question': '查找会议：保密部门检索词'}).json()['sources']
    assert client.get(f'/api/meetings/{hidden["id"]}').status_code == 404


@pytest.mark.parametrize('publisher_role,owner_department,expected_tasks', [('MANAGER', 'tech', 1), ('MANAGER', 'product', 0), ('EMPLOYEE', 'tech', 0)])
def test_worker_rechecks_manager_role_and_assignment_before_publication(client, db, team, publisher_role, owner_department, expected_tasks):
    from app.ai.demo import DEMO_TEXT
    login(client, team['manager'])
    m = meeting(client, [team['zhangsan'].id, team['lisi'].id])
    response = client.post(f'/api/meetings/{m["id"]}/inputs', json={'request_id': str(uuid4()), 'text': DEMO_TEXT})
    assert response.status_code == 202
    team['manager'].role = publisher_role
    if owner_department == 'product':
        team['zhangsan'].department_id = team['other'].department_id
    db.commit()
    class Borrow:
        def __enter__(self): return db
        def __exit__(self, *args): return False
    worker = AnalysisWorker(DemoAnalysisAdapter(), session_factory=Borrow)
    asyncio.run(worker.graph.ainvoke({'job_id': response.json()['job_id']}))
    assert len(list(db.scalars(select(Task).where(Task.meeting_id == m['id'])))) == expected_tasks
    login(client, 'boss')
    rows = client.get(f'/api/meetings/{m["id"]}/candidates').json()['items']
    if expected_tasks == 0:
        assert rows[0]['status'] == 'NEEDS_INFO'
    else:
        assert rows[0]['status'] == 'PUBLISHED'
        login(client, team['manager'])
        candidate_id = rows[1]['id']
        payload = {'title': '整理测试用例', 'owner_id': team['wangwu'].id, 'source_excerpt': '需要有人整理测试用例，暂未确定负责人。'}
        assert client.post(f'/api/candidates/{candidate_id}/publish', json=payload).status_code == 403
        payload['owner_id'] = team['lisi'].id
        result = client.post(f'/api/candidates/{candidate_id}/publish', json=payload)
        assert result.status_code == 200, result.text
        assert result.json()['can_manage']
        assert 'raw_output' not in client.get(f'/api/meetings/{m["id"]}/analysis').json()
        login(client, team['other'])
        assert client.post(f'/api/candidates/{candidate_id}/dismiss').status_code == 404


def test_candidates_and_retry_cannot_manage_boss_meeting(client, db, team):
    from app.ai.demo import DEMO_TEXT
    login(client, 'boss')
    m = meeting(client, [team['manager'].id])
    response = client.post(f'/api/meetings/{m["id"]}/inputs', json={'request_id': str(uuid4()), 'text': DEMO_TEXT})
    from app.models import ProcessingJob
    job = db.get(ProcessingJob, response.json()['job_id'])
    job.status = 'FAILED'
    db.commit()
    login(client, team['manager'])
    assert client.post(f'/api/jobs/{job.id}/retry').status_code == 403
