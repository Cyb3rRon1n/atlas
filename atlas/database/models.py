from datetime import datetime

from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column


class Base(DeclarativeBase):
    pass


class EventRecord(Base):

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    event_type: Mapped[str]

    source: Mapped[str]

    payload: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )


class EnvironmentRecord(Base):

    __tablename__ = "environment"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    data: Mapped[str]

    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow
    )
