import json

from sqlalchemy.orm import Session

from atlas.database.engine import engine
from atlas.database.models import (
    EventRecord,
    EnvironmentRecord
)


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


    def latest_environment(self):

        with Session(engine) as session:

            record = (
                session.query(EnvironmentRecord)
                .order_by(
                    EnvironmentRecord.created_at.desc()
                )
                .first()
            )

            if not record:
                return None

            return json.loads(
                record.data
            )
