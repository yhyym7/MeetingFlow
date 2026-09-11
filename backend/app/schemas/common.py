from typing import Annotated, ClassVar, Generic, TypeVar

from fastapi import Query
from pydantic import BaseModel, ConfigDict, model_validator


PageNumber = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PartialUpdate(BaseModel):
    """Only fields explicitly listed in nullable_fields may be cleared."""
    model_config = ConfigDict(extra="forbid")
    nullable_fields: ClassVar[set[str]] = set()

    @model_validator(mode="after")
    def validate_supplied_fields(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in self.nullable_fields:
                raise ValueError(f"{field} 不能为 null")
        return self
