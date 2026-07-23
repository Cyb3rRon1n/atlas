from pydantic import BaseModel
from datetime import datetime


class Inventory(BaseModel):
    created: str
    hostname: str
    data: dict
