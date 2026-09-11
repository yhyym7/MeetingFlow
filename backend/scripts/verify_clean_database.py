"""Isolated empty-MySQL install check. Never drops an existing project database."""
import asyncio
import os
import subprocess
import sys
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import get_settings


def main():
    original = make_url(get_settings().database_url.get_secret_value())
    name = 'meetingflow_check_' + uuid4().hex[:12]
    assert name != original.database and name.startswith('meetingflow_check_') and len(name) == 30
    admin = create_engine(original.set(database=None), isolation_level='AUTOCOMMIT', hide_parameters=True)
    created = False
    try:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci')
            created = True
        os.environ['MEETINGFLOW_DATABASE_URL'] = original.set(database=name).render_as_string(hide_password=False)
        os.environ['MEETINGFLOW_ANALYSIS_MODE'] = 'demo'
        os.environ['MEETINGFLOW_ASR_MODE'] = 'unconfigured'
        os.environ['MEETINGFLOW_EMBEDDING_MODE'] = 'keyword'
        get_settings.cache_clear()
        subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], check=True)
        from app.database import get_engine
        from app.models import User
        from scripts.seed_demo import seed_demo
        password = 'temporary-' + uuid4().hex
        with Session(get_engine()) as db:
            seed_demo(db, password)
            db.commit()
            person_id = db.scalar(select(User.id).where(User.username == 'zhangsan'))
        from app.main import create_app
        from app.ai.demo import DEMO_TEXT, DemoAnalysisAdapter
        from app.ai.workflow import AnalysisWorker
        with TestClient(create_app(start_worker=False), headers={'Origin':'http://127.0.0.1:5173'}) as client:
            assert client.post('/api/auth/login',json={'username':'boss','password':password}).status_code == 200
            meeting = client.post('/api/meetings', json={'title':'空库安装验证','starts_at':'2026-09-11T10:00:00+08:00','participant_ids':[person_id]}).json()
            submission = client.post(f"/api/meetings/{meeting['id']}/inputs",json={'request_id':str(uuid4()),'text':DEMO_TEXT}).json()
            assert asyncio.run(AnalysisWorker(DemoAnalysisAdapter()).run_next())
            assert client.get(f"/api/jobs/{submission['job_id']}").json()['status'] == 'SUCCEEDED'
            task = client.get(f"/api/meetings/{meeting['id']}/tasks").json()['items'][0]
            assert client.post('/api/auth/login',json={'username':'zhangsan','password':password}).status_code == 200
            assert client.patch(f"/api/tasks/{task['id']}/status",json={'status':'DONE'}).status_code == 200
            assert client.get(f"/api/tasks/{task['id']}").json()['status'] == 'DONE'
        print('PASS: all migrations from empty MySQL, initialization, login, demo analysis, automatic task and employee completion. No paid model calls.')
    finally:
        from app.database import get_engine
        get_engine().dispose()
        get_engine.cache_clear()
        if created:
            with admin.connect() as connection:
                connection.exec_driver_sql(f'DROP DATABASE `{name}`')
        admin.dispose()


if __name__ == '__main__':
    main()
