from typing import List, Optional

from pydantic import BaseModel, Field


class EquipmentItem(BaseModel):
    equip: bool
    id: int
    star: int


class ResultItem(BaseModel):
    id: str
    atk: List[EquipmentItem]
    def_: List[EquipmentItem] = Field(alias="def")
    iseditor: bool
    private: bool
    group: bool
    updated: str
    up: int
    down: int
    comment: Optional[str]
    liked: bool
    disliked: bool


class PageInfo(BaseModel):
    page: int
    hasMore: bool


class DataContent(BaseModel):
    result: List[ResultItem]
    page: PageInfo


class PcrfansResponse(BaseModel):
    code: int
    message: str
    data: DataContent
    version: str


class AttackData(BaseModel):
    atk: List[int]
    def_: List[int] = Field(alias="def")
    up: int = 0
    down: int = 0
