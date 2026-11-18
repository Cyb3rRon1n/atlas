from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from lanxang.clock import utcnow


@dataclass
class AtlasEvent:
    """
    Represents an event occurring within Lanxang.
    """

    event_type: str
    source: str
    payload: Any

    timestamp: datetime = field(
        default_factory=utcnow
    )
