from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


LoginName = Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NewPassword = Annotated[str, StringConstraints(min_length=8, max_length=256)]


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class DepartmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: DisplayName


class PublicUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    department_id: int | None


class AdminUserOut(PublicUserOut):
    username: str
    role: Literal["BOSS", "EMPLOYEE", "MANAGER"]
    is_active: bool


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: LoginName
    name: DisplayName
    department_id: int | None = Field(default=None, gt=0)
    role: Literal["BOSS", "EMPLOYEE", "MANAGER"] = "EMPLOYEE"
    password: NewPassword


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: DisplayName | None = None
    department_id: int | None = Field(default=None, gt=0)
    role: Literal["BOSS", "EMPLOYEE", "MANAGER"] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_null_non_nullable_fields(self):
        for field in self.model_fields_set - {"department_id"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
