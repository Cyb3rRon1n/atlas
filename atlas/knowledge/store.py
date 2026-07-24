import json

from sqlalchemy.orm import Session

from atlas.database.engine import engine
from atlas.database.models import EventRecord
from atlas.events import AtlasEvent


class KnowledgeStore:
    """
    Stores Atlas events permanently.
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
