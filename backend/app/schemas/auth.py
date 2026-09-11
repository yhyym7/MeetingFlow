from pydantic import BaseModel, ConfigDict, Field

from app.schemas.people import LoginName


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: LoginName
    password: str = Field(min_length=1, max_length=256)
