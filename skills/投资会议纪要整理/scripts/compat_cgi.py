#!/usr/bin/env python3
"""Small FieldStorage fallback for Python builds without stdlib cgi."""

from __future__ import annotations

import io
import urllib.parse
from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Any


class Field:
    def __init__(self, *, filename: str | None = None, value: str = "", data: bytes = b"", content_type: str = "") -> None:
        self.filename = filename
        self.value = value
        self.file = io.BytesIO(data)
        self.type = content_type


class FieldStorage:
    def __init__(
        self,
        fp: Any,
        headers: Any,
        environ: dict[str, str] | None = None,
        keep_blank_values: bool = False,
        **_: Any,
    ) -> None:
        self._fields: dict[str, Field | list[Field]] = {}
        environ = environ or {}
        content_type = environ.get("CONTENT_TYPE") or headers.get("Content-Type", "")
        length_raw = environ.get("CONTENT_LENGTH") or headers.get("Content-Length", "0") or "0"
        try:
            length = int(length_raw)
        except ValueError:
            length = 0
        body = fp.read(length) if length else b""
        if "multipart/form-data" in content_type:
            self._parse_multipart(content_type, body)
        else:
            self._parse_urlencoded(body, keep_blank_values=keep_blank_values)

    def _add(self, name: str, field: Field) -> None:
        current = self._fields.get(name)
        if current is None:
            self._fields[name] = field
        elif isinstance(current, list):
            current.append(field)
        else:
            self._fields[name] = [current, field]

    def _parse_multipart(self, content_type: str, body: bytes) -> None:
        message = BytesParser(policy=email_policy).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        )
        if not message.is_multipart():
            return
        for part in message.iter_parts():
            if part.get_content_disposition() != "form-data":
                continue
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                self._add(name, Field(filename=filename, data=payload, content_type=part.get_content_type()))
                continue
            charset = part.get_content_charset() or "utf-8"
            self._add(name, Field(value=payload.decode(charset, errors="replace")))

    def _parse_urlencoded(self, body: bytes, *, keep_blank_values: bool) -> None:
        text = body.decode("utf-8", errors="replace")
        parsed = urllib.parse.parse_qs(text, keep_blank_values=keep_blank_values)
        for name, values in parsed.items():
            for value in values:
                self._add(name, Field(value=value))

    def keys(self) -> list[str]:
        return list(self._fields.keys())

    def getfirst(self, key: str, default: str = "") -> str:
        value = self._fields.get(key)
        if value is None:
            return default
        field = value[0] if isinstance(value, list) else value
        return field.value

    def __contains__(self, key: str) -> bool:
        return key in self._fields

    def __getitem__(self, key: str) -> Field | list[Field]:
        return self._fields[key]
