import json

from sqlalchemy.orm import Session

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


    def latest_analysis(self):

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
