"""Token extraction, path cleaning, text normalization, and URL helpers for ZaiManhua."""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Codepoint mapping for Windows-1252 / Latin-1 mis-decoded UTF-8 sequences
CP1252_MAP = {
    0x20AC: 0x80,
    0x201A: 0x82,
    0x0192: 0x83,
    0x201E: 0x84,
    0x2026: 0x85,
    0x2020: 0x86,
    0x2021: 0x87,
    0x02C6: 0x88,
    0x2030: 0x89,
    0x0160: 0x8A,
    0x2039: 0x8B,
    0x0152: 0x8C,
    0x017D: 0x8E,
    0x2018: 0x91,
    0x2019: 0x92,
    0x201C: 0x93,
    0x201D: 0x94,
    0x2022: 0x95,
    0x2013: 0x96,
    0x2014: 0x97,
    0x02DC: 0x98,
    0x2122: 0x99,
    0x0161: 0x9A,
    0x203A: 0x9B,
    0x0153: 0x9C,
    0x017E: 0x9E,
    0x0178: 0x9F,
}

MOJIBAKE_MARKERS_SET = frozenset(
    {"ç", "¬", "å", "Ã", "Â", "é", "è", "æ", "§", "°", "¶", "·", "ä", "¸", "Š", "œ"}
)


def extract_token(token_or_auth: str) -> str:
    """Normalize token string from 'Bearer <jwt>', 'Token <jwt>', quotes, or raw JWT."""
    raw = token_or_auth.strip().strip("\"'")
    if raw.lower().startswith("bearer "):
        raw = raw[7:].strip().strip("\"'")
    elif raw.lower().startswith("token "):
        raw = raw[6:].strip().strip("\"'")
    return raw


def clean_path(path_str: str) -> str:
    """Strip surrounding whitespace and quotes from a filesystem path."""
    return path_str.strip().strip("\"'")


def normalize_comic_url(comic_id: Any) -> str:
    """Format comic ID as Mihon manga URL string (e.g. '77022')."""
    if comic_id is None:
        return ""
    clean = str(comic_id).strip().strip("/")
    return clean


def normalize_chapter_url(comic_id: Any, chapter_id: Any) -> str:
    """Format chapter or reading record as Mihon chapter URL string (e.g. '77022/174034')."""
    c_id = normalize_comic_url(comic_id)
    ch_id = str(chapter_id).strip().strip("/") if chapter_id is not None else ""
    if not c_id:
        return ""
    if not ch_id:
        return c_id
    if "/" in ch_id:
        return ch_id
    return f"{c_id}/{ch_id}"


def repair_mojibake(text: Optional[str]) -> str:
    """Detect and repair UTF-8 text incorrectly decoded as Latin-1 or CP1252."""
    if not text:
        return ""

    if not (MOJIBAKE_MARKERS_SET & set(text)):
        return text

    for encoding in ("latin1", "cp1252"):
        try:
            return text.encode(encoding).decode("utf-8")
        except Exception:
            pass

    try:
        raw_bytes = bytearray()
        for char in text:
            code = ord(char)
            if code < 256:
                raw_bytes.append(code)
            elif code in CP1252_MAP:
                raw_bytes.append(CP1252_MAP[code])
            else:
                raise ValueError("Char outside 8-bit / CP1252 range")
        return raw_bytes.decode("utf-8")
    except Exception:
        pass

    replacements = {
        "ç¬¬": "第",
        "è©±": "話",
        "è¯": "话",
        "å ·": "卷",
        "å·»": "卷",
        "å®Œ": "完",
        "ä¸Š": "上",
        "ä¸‹": "下",
        "ä¸": "中",
        "è¯•çœ‹": "试看",
    }
    res = text
    for k, v in replacements.items():
        res = res.replace(k, v)
    return res
