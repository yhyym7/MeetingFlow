"""Versioned, exact source slices. No embedding provider is configured yet."""
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models import MeetingChunk, MeetingInput


def split_text(text: str):
    start = 0
    while start < len(text):
        end = min(start + 600, len(text))
        if end < len(text):
            boundary = text.rfind("\n", max(start + 300, end - 150), end)
            if boundary >= 0:
                end = boundary + 1
        yield start, end, text[start:end]
        if end == len(text):
            break
        start = end - 100


def index_input(db: Session, record: MeetingInput) -> int:
    # Call while holding the parent meeting lock; slices commit with their input.
    chunks = [MeetingChunk(input_id=record.id, position=position, start_offset=start,
                           end_offset=end, text=text)
              for position, (start, end, text) in enumerate(split_text(record.text))]
    db.add_all(chunks)
    return len(chunks)


def backfill_chunks(db: Session) -> int:
    from app.models import Meeting
    missing = list(db.scalars(select(MeetingInput.id).where(~exists(
        select(MeetingChunk.id).where(MeetingChunk.input_id == MeetingInput.id)))))
    count = 0
    for input_id in missing:
        record = db.get(MeetingInput, input_id)
        db.scalar(select(Meeting.id).where(Meeting.id == record.meeting_id).with_for_update())
        if db.scalar(select(MeetingChunk.id).where(MeetingChunk.input_id == input_id).limit(1)) is None:
            count += index_input(db, record)
            db.flush()
    db.commit()
    return count
