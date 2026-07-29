import json

from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import (
    EventRecord,
    EnvironmentRecord,
    AnalysisRecord
)


class KnowledgeQueries:
    """
    Query Atlas historical knowledge.
    """

    def recent_events(
        self,
        limit: int = 10
    ):

        initialize_database(engine)

        with Session(engine) as session:

            return (
                session.query(EventRecord)
                .order_by(
                    EventRecord.created_at.desc()
                )
                .limit(limit)
                .all()
            )


    def environment_history(
        self,
        limit: int = 20
    ):

        initialize_database(engine)

        with Session(engine) as session:

            records = (
                session.query(EnvironmentRecord)
                .order_by(
                    EnvironmentRecord.created_at.desc(),
                    EnvironmentRecord.id.desc()
                )
                .limit(limit)
                .all()
            )

            return [
                {
                    "created_at": record.created_at,
                    "data": json.loads(record.data)
                }
                for record in records
            ]


    def latest_environment(self):

        initialize_database(engine)

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


    def latest_analysis(self):

        initialize_database(engine)

        with Session(engine) as session:

            record = (
                session.query(AnalysisRecord)
                .order_by(
                    AnalysisRecord.created_at.desc()
                )
                .first()
            )

            if not record:
                return None

            return {
                "summary": record.summary,
                "recommendations": json.loads(
                    record.recommendations
                ),
                "provider": record.provider,
                "model": record.model,
                "created_at": str(record.created_at)
            }
