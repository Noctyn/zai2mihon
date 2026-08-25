"""Data models for Mihon backup domain entities and ZaiManhua constants."""

from __future__ import annotations

import time
from typing import List, Optional
from pydantic import BaseModel, Field

DEFAULT_ZAIMANHUA_SOURCE_ID = 524579092615598717
DEFAULT_ZAIMANHUA_SOURCE_NAME = "再漫画"


class MihonCategory(BaseModel):
    name: str
    id: int = 1
    order: int = 0
    flags: int = 0


class MihonSource(BaseModel):
    source_id: int = DEFAULT_ZAIMANHUA_SOURCE_ID
    name: str = DEFAULT_ZAIMANHUA_SOURCE_NAME


class MihonChapter(BaseModel):
    url: str
    name: str
    scanlator: Optional[str] = None
    read: bool = True
    bookmark: bool = False
    last_page_read: int = 0
    date_fetch: int = Field(default_factory=lambda: int(time.time() * 1000))
    date_upload: int = Field(default_factory=lambda: int(time.time() * 1000))
    chapter_number: float = 0.0
    source_order: int = 0
    last_modified_at: Optional[int] = None
    version: Optional[int] = None
    memo: List[bytes] = Field(default_factory=lambda: [b"{}"])


class MihonHistory(BaseModel):
    url: str
    last_read: int = Field(default_factory=lambda: int(time.time() * 1000))
    read_duration: int = 0


class MihonManga(BaseModel):
    source: int = DEFAULT_ZAIMANHUA_SOURCE_ID
    url: str
    title: str
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    genre: List[str] = Field(default_factory=list)
    status: int = 1  # 1 = ONGOING, 2 = COMPLETED
    thumbnail_url: Optional[str] = None
    date_added: int = Field(default_factory=lambda: int(time.time() * 1000))
    viewer_flags: int = 0
    chapter_flags: int = 513
    update_strategy: int = 0
    favorite: bool = True
    initialized: bool = True
    version: Optional[int] = None
    categories: List[int] = Field(default_factory=list)
    chapters: List[MihonChapter] = Field(default_factory=list)
    history: List[MihonHistory] = Field(default_factory=list)
    memo: List[bytes] = Field(default_factory=lambda: [b"{}"])


class MihonBackup(BaseModel):
    backup_manga: List[MihonManga] = Field(default_factory=list)
    backup_categories: List[MihonCategory] = Field(default_factory=list)
    backup_sources: List[MihonSource] = Field(default_factory=list)
