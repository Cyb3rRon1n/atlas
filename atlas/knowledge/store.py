import json
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from atlas.database import initialize_database
from atlas.database.engine import engine
from atlas.database.models import EventRecord, EnvironmentRecord, AnalysisRecord
from atlas.events import AtlasEvent
from atlas.intelligence.providers import AnalysisResult


ENVIRONMENT_KEEP = timedelta(days=7)
EVENTS_KEEP = timedelta(days=90)


class KnowledgeStore:
    """
    Stores Atlas knowledge permanently.
    """

    def save_event(
        self,
        event: AtlasEvent
    ):

        initialize_database(engine)

        with Session(engine) as session:

            record = EventRecord(
                event_type=event.event_type,
                source=event.source,
                payload=json.dumps(
                    event.payload
                )
            )

            session.add(record)

            session.commit()


    def save_environment(
        self,
        environment
    ):

        initialize_database(engine)

        with Session(engine) as session:

            record = EnvironmentRecord(
                data=json.dumps(
                    environment.summary()
                )
            )

            session.add(record)

            session.commit()

        self.prune(datetime.utcnow())


    def prune(self, now):
        """
        Old rows out, once per environment save (each scan): environment
        snapshots after 7 days (pages read only the newest), events after
        90 days (Trends reads 30) - except the newest event of each type,
        which some pages read however old it is.
        """

        with Session(engine) as session, session.begin():

            session.execute(delete(EnvironmentRecord).where(EnvironmentRecord.created_at < now - ENVIRONMENT_KEEP))

            newest = select(func.max(EventRecord.id)).group_by(EventRecord.event_type)
            session.execute(delete(EventRecord).where(EventRecord.created_at < now - EVENTS_KEEP,
                                                      EventRecord.id.not_in(newest)))


    def save_analysis(
        self,
        result: AnalysisResult,
        provider: str,
        model: str
    ):

        initialize_database(engine)

        with Session(engine) as session:

            record = AnalysisRecord(
                summary=result.summary,
                recommendations=json.dumps(
                    [
                        {
                            "title": item.title,
                            "detail": item.detail,
                            "severity": item.severity,
                            "action": (
                                {
                                    "type": item.action.type,
                                    "target": item.action.target
                                }
                                if item.action else None
                            )
                        }
                        for item in result.recommendations
                    ]
                ),
                provider=provider,
                model=model
            )

            session.add(record)

            session.commit()
