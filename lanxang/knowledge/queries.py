import json

from sqlalchemy.orm import Session

from lanxang.database import initialize_database
from lanxang.database.engine import engine
from lanxang.database.models import (
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


    def events_since(self, event_types, since):
        """[(created_at, parsed payload)] of the given types since `since`, oldest first - Trends charts."""

        initialize_database(engine)

        with Session(engine) as session:

            rows = (
                session.query(EventRecord.created_at, EventRecord.payload)
                .filter(EventRecord.event_type.in_(list(event_types)), EventRecord.created_at >= since)
                .order_by(EventRecord.created_at)
                .all()
            )

            return [(created_at, json.loads(payload) if payload else {}) for created_at, payload in rows]


    def latest_event_payload(self, event_type: str):
        """
        Parsed payload of the newest event of one type, or None.
        """

        initialize_database(engine)

        with Session(engine) as session:

            record = (
                session.query(EventRecord)
                .filter(EventRecord.event_type == event_type)
                .order_by(EventRecord.created_at.desc(), EventRecord.id.desc())
                .first()
            )

            return json.loads(record.payload) if record and record.payload else None


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
        """
        The newest picture of the environment. Each atlas-scan command saves only its own part (the map: topology;
        a Proxmox scan: virtualization) and leaves the rest empty, so a part the newest row lacks is taken from
        the most recent row that has it. Stored rows stay as saved - the trends read them one by one.
        """

        rows = self.environment_history(limit=200)

        if not rows:
            return None

        latest = dict(rows[0]["data"])

        for row in rows[1:]:
            for key, value in row["data"].items():
                if key != "timestamp" and latest.get(key) in (None, {}, []) and value not in (None, {}, []):
                    latest[key] = value

        return latest


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

    def latest_topology(self):
        """
        Newest saved network map. Every command saves only its own categories,
        so the newest row overall is usually not the one atlas map wrote.
        """

        for row in self.environment_history(limit=200):

            topology = row["data"].get("topology")

            if topology:
                return topology

        return None
