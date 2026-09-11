"""Run after migrations to index existing input versions without changing meetings."""
from sqlalchemy.orm import Session

from app.database import get_engine
from app.services.knowledge import backfill_chunks


if __name__ == "__main__":
    with Session(get_engine()) as db:
        print(f"Added {backfill_chunks(db)} meeting source chunks.")
