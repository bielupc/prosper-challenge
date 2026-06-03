from datetime import datetime, timezone

from sqlalchemy import Column, DateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz_column() -> Column:
    return Column(DateTime(timezone=True), nullable=False)
