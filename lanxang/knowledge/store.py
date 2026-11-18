import json
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from lanxang.database import initialize_database
from lanxang.database.engine import engine
from lanxang.database.models import EventRecord, EnvironmentRecord, AnalysisRecord
from lanxang.events import AtlasEvent
from lanxang.intelligence.providers import AnalysisResult
from lanxang.clock import utcnow


ENVIRONMENT_KEEP = timedelta(days=7)
EVENTS_KEEP = timedelta(days=90)
# Routine bookkeeping with no history reader (each repeats the system snapshot every scan): a week is plenty.
ROUTINE_EVENTS = ("atlas.discovery.completed", "atlas.plugins.discovery.completed", "atlas.plugin.loaded")
ROUTINE_KEEP = timedelta(days=7)


class KnowledgeStore:
    """
    Stores Lanxang knowledge permanently.
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

        self.prune(utcnow())


    def prune(self, now):
        """
        Old rows out, once per environment save (each scan): environment
        snapshots after 7 days (pages read only the newest), events after
        90 days (Trends reads 30), routine discovery/plugin events after 7 - except the newest event of each type,
        which some pages read however old it is.
        """

        with Session(engine) as session, session.begin():

            session.execute(delete(EnvironmentRecord).where(EnvironmentRecord.created_at < now - ENVIRONMENT_KEEP))

            newest = select(func.max(EventRecord.id)).group_by(EventRecord.event_type)
            session.execute(delete(EventRecord).where(EventRecord.created_at < now - EVENTS_KEEP,
                                                      EventRecord.id.not_in(newest)))
            session.execute(delete(EventRecord).where(EventRecord.created_at < now - ROUTINE_KEEP,
                                                      EventRecord.event_type.in_(ROUTINE_EVENTS),
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
