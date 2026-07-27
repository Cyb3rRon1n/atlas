import json

from sqlalchemy.orm import Session

from atlas.database.engine import engine
from atlas.database.models import EventRecord, EnvironmentRecord, AnalysisRecord
from atlas.events import AtlasEvent
from atlas.intelligence.providers import AnalysisResult


class KnowledgeStore:
    """
    Stores Atlas knowledge permanently.
    """

    def save_event(
        self,
        event: AtlasEvent
    ):

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

        with Session(engine) as session:

            record = EnvironmentRecord(
                data=json.dumps(
                    environment.summary()
                )
            )

            session.add(record)

            session.commit()


    def save_analysis(
        self,
        result: AnalysisResult,
        provider: str,
        model: str
    ):

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
