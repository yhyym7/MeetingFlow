"""Add two fictional managers, preserving existing people and their passwords."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import User


def seed_managers(db: Session):
    for username, name, employee_name in [('tech_manager', '陈部长', 'zhangsan'), ('product_manager', '周部长', 'wangwu')]:
        if db.scalar(select(User.id).where(User.username == username)) is not None:
            continue
        employee = db.scalar(select(User).where(User.username == employee_name))
        if employee is None or employee.department_id is None:
            raise RuntimeError('请先初始化基础演示人员及部门')
        db.add(User(username=username, name=name, role='MANAGER', department_id=employee.department_id,
                    password_hash=employee.password_hash, is_active=True))
    db.commit()


if __name__ == '__main__':
    with Session(get_engine()) as db:
        seed_managers(db)
    print('Manager demo accounts ready: tech_manager, product_manager. Existing accounts preserved.')
