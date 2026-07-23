from pydantic import BaseModel


class ComposeService(BaseModel):
    name: str
    image: str | None = None
    ports: list[str] = []
    volumes: list[str] = []


class ComposeProject(BaseModel):
    name: str
    services: list[ComposeService]
