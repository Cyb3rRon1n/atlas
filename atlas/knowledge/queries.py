from sqlalchemy.orm import Session

from atlas.database.engine import engine
from atlas.database.models import EventRecord


class KnowledgeQueries:
    """
    Query Atlas historical knowledge.
    """

    def recent_events(
        self,
        limit: int = 10
    ):

        with Session(engine) as session:

            return (
                session.query(EventRecord)
                .order_by(
                    EventRecord.created_at.desc()
                )
                .limit(limit)
                .all()
            )
