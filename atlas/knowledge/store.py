import json

from sqlalchemy.orm import Session

from atlas.database.engine import engine
from atlas.database.models import EventRecord, EnvironmentRecord
from atlas.events import AtlasEvent


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
