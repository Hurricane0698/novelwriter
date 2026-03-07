# SPDX-FileCopyrightText: 2026 Isaac.X.Ω.Yuan
# SPDX-License-Identifier: AGPL-3.0-only

"""
Character card parsing utilities.

Supports common JSON and PNG-based card formats without external dependencies.
"""

from __future__ import annotations

import base64
import binascii
import json
import struct
import zlib
from typing import Any, Dict, List, Optional, Tuple


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def parse_character_card(content: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Parse a character card from JSON or PNG content.

    Returns a normalized dict with common fields.
    """
    if not content:
        raise ValueError("Character card file is empty.")

    filename = filename or ""
    trimmed = content.lstrip()

    if filename.lower().endswith(".json") or trimmed.startswith(b"{") or trimmed.startswith(b"["):
        raw = _parse_json_bytes(content)
        return _normalize_card(raw)

    if content.startswith(PNG_SIGNATURE):
        raw = _parse_png_card(content)
        return _normalize_card(raw)

    raise ValueError("Unsupported character card format. Upload a .json or .png card.")


def build_character_content(card: Dict[str, Any]) -> str:
    """Build lorebook-ready content text from normalized card data."""
    sections = []

    def add_section(label: str, value: str) -> None:
        if value:
            sections.append(f"{label}: {value}")

    add_section("Description", card.get("description", ""))
    add_section("Personality", card.get("personality", ""))
    add_section("Scenario", card.get("scenario", ""))
    add_section("First Message", card.get("first_mes", ""))
    add_section("Example Dialogue", card.get("mes_example", ""))
    add_section("Creator Notes", card.get("creator_notes", ""))
    add_section("System Prompt", card.get("system_prompt", ""))
    add_section("Post-History Instructions", card.get("post_history_instructions", ""))

    return "\n".join(sections).strip()


def extract_character_keywords(card: Dict[str, Any]) -> List[str]:
    """Extract keyword triggers from normalized card data."""
    keywords: List[str] = []

    def add_keyword(value: str) -> None:
        value = value.strip()
        if value and value not in keywords:
            keywords.append(value)

    name = card.get("name", "")
    if isinstance(name, str):
        add_keyword(name)

    for alias in card.get("aliases", []) or []:
        if isinstance(alias, str):
            add_keyword(alias)

    return keywords


def _parse_json_bytes(content: bytes) -> Dict[str, Any]:
    encodings = ["utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "latin-1"]
    last_error = None
    for encoding in encodings:
        try:
            text = content.decode(encoding)
            return json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            last_error = exc
    raise ValueError("Invalid JSON character card.") from last_error


def _parse_png_card(content: bytes) -> Dict[str, Any]:
    payloads = _extract_png_text_payloads(content)
    if not payloads:
        raise ValueError("No text payloads found in PNG character card.")

    # Preferred keys commonly used by character cards.
    preferred_keys = ("chara", "character", "card", "ccv2")
    for key in preferred_keys:
        if key in payloads:
            decoded = _decode_card_payload(payloads[key])
            if decoded is not None:
                return decoded

    # Fallback: try any payload that looks like JSON/base64 JSON.
    for payload in payloads.values():
        decoded = _decode_card_payload(payload)
        if decoded is not None:
            return decoded

    raise ValueError("Unable to decode character card data from PNG.")


def _extract_png_text_payloads(content: bytes) -> Dict[str, str]:
    payloads: Dict[str, str] = {}
    if not content.startswith(PNG_SIGNATURE):
        return payloads

    offset = len(PNG_SIGNATURE)
    data_len = len(content)

    while offset + 8 <= data_len:
        length = struct.unpack(">I", content[offset:offset + 4])[0]
        chunk_type = content[offset + 4:offset + 8]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + length

        if chunk_data_end + 4 > data_len:
            break

        chunk_data = content[chunk_data_start:chunk_data_end]
        chunk_name = chunk_type.decode("ascii", errors="replace")

        if chunk_name == "tEXt":
            key, text = _parse_text_chunk(chunk_data)
            if key:
                payloads[key.lower()] = text
        elif chunk_name == "zTXt":
            key, text = _parse_ztxt_chunk(chunk_data)
            if key:
                payloads[key.lower()] = text
        elif chunk_name == "iTXt":
            key, text = _parse_itxt_chunk(chunk_data)
            if key:
                payloads[key.lower()] = text

        offset = chunk_data_end + 4  # Skip CRC

    return payloads


def _parse_text_chunk(chunk_data: bytes) -> Tuple[str, str]:
    try:
        key, text = chunk_data.split(b"\x00", 1)
    except ValueError:
        return "", ""
    return key.decode("latin-1", errors="ignore"), text.decode("latin-1", errors="ignore")


def _parse_ztxt_chunk(chunk_data: bytes) -> Tuple[str, str]:
    try:
        key, rest = chunk_data.split(b"\x00", 1)
    except ValueError:
        return "", ""
    if not rest:
        return "", ""
    compression_method = rest[0]
    if compression_method != 0:
        return "", ""
    compressed_text = rest[1:]
    try:
        text = zlib.decompress(compressed_text).decode("utf-8", errors="ignore")
    except zlib.error:
        return "", ""
    return key.decode("latin-1", errors="ignore"), text


def _parse_itxt_chunk(chunk_data: bytes) -> Tuple[str, str]:
    try:
        key, rest = chunk_data.split(b"\x00", 1)
    except ValueError:
        return "", ""
    if len(rest) < 2:
        return "", ""

    compression_flag = rest[0]
    compression_method = rest[1]
    rest = rest[2:]

    # Skip language tag
    try:
        _, rest = rest.split(b"\x00", 1)
        _, rest = rest.split(b"\x00", 1)  # translated keyword
    except ValueError:
        return "", ""

    text_bytes = rest
    if compression_flag == 1:
        if compression_method != 0:
            return "", ""
        try:
            text_bytes = zlib.decompress(text_bytes)
        except zlib.error:
            return "", ""

    return key.decode("latin-1", errors="ignore"), text_bytes.decode("utf-8", errors="ignore")


def _decode_card_payload(payload: str) -> Optional[Dict[str, Any]]:
    payload = payload.strip()
    if not payload:
        return None

    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        pass

    compact = "".join(payload.split())
    padding = len(compact) % 4
    if padding:
        compact += "=" * (4 - padding)

    try:
        decoded = base64.b64decode(compact, validate=False)
    except (ValueError, binascii.Error):
        return None

    try:
        decoded_text = decoded.decode("utf-8", errors="ignore")
    except UnicodeDecodeError:
        return None

    try:
        return json.loads(decoded_text)
    except json.JSONDecodeError:
        return None


def _normalize_card(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("Character card JSON must be an object.")

    data = raw
    if isinstance(raw.get("data"), dict):
        data = raw["data"]
    elif isinstance(raw.get("character"), dict):
        data = raw["character"]

    name = _first_text(data, ["name", "character_name", "char_name", "display_name"])
    description = _first_text(data, ["description", "desc", "summary"])
    personality = _first_text(data, ["personality"])
    scenario = _first_text(data, ["scenario", "world_scenario"])
    first_mes = _first_text(data, ["first_mes", "first_message", "greeting"])
    mes_example = _first_text(data, ["mes_example", "example_dialogue", "example"])
    creator_notes = _first_text(data, ["creator_notes", "commentary", "notes"])
    system_prompt = _first_text(data, ["system_prompt", "system"])
    post_history = _first_text(data, ["post_history_instructions", "post_history"])

    return {
        "name": name,
        "description": description,
        "personality": personality,
        "scenario": scenario,
        "first_mes": first_mes,
        "mes_example": mes_example,
        "creator_notes": creator_notes,
        "system_prompt": system_prompt,
        "post_history_instructions": post_history,
        "tags": _coerce_list(data.get("tags")),
        "aliases": _coerce_list(
            data.get("aliases")
            or data.get("alternate_names")
            or data.get("alt_names")
            or data.get("nicknames")
        ),
        "alternate_greetings": _coerce_list(
            data.get("alternate_greetings")
            or data.get("alternative_greetings")
        ),
        "raw": raw,
    }


def _first_text(data: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    return ""


def _coerce_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return [str(value).strip()] if str(value).strip() else []
