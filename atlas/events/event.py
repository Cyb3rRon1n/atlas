from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class AtlasEvent:
    """
    Represents an event occurring within Atlas.
    """

    event_type: str
    source: str
    payload: Any

    timestamp: datetime = field(
        default_factory=datetime.utcnow
    )
