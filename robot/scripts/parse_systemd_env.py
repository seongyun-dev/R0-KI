#!/usr/bin/env python3
"""Safely emit a systemd-style EnvironmentFile as NUL-delimited assignments."""

from __future__ import annotations

import re
import sys
from pathlib import Path


VARIABLE_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class EnvironmentFileError(ValueError):
    """Raised when an environment file cannot be parsed safely."""


def _parse_double_quoted(value: str, line_number: int) -> str:
    parsed: list[str] = []
    index = 1
    while index < len(value):
        character = value[index]
        if character == '"':
            if value[index + 1 :].strip():
                raise EnvironmentFileError(
                    f"line {line_number}: unexpected text after quoted value"
                )
            return "".join(parsed)
        if character == "\\":
            index += 1
            if index >= len(value):
                raise EnvironmentFileError(
                    f"line {line_number}: dangling escape in quoted value"
                )
            escaped = value[index]
            if escaped in {'"', "\\", "`", "$"}:
                parsed.append(escaped)
            else:
                parsed.extend(("\\", escaped))
        else:
            parsed.append(character)
        index += 1
    raise EnvironmentFileError(f"line {line_number}: unterminated double quote")


def _parse_unquoted(value: str, line_number: int) -> str:
    parsed: list[str] = []
    index = 0
    while index < len(value):
        character = value[index]
        if character == "\\":
            index += 1
            if index >= len(value):
                raise EnvironmentFileError(
                    f"line {line_number}: dangling escape in unquoted value"
                )
            character = value[index]
        parsed.append(character)
        index += 1
    return "".join(parsed)


def _parse_value(raw_value: str, line_number: int) -> str:
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith("'"):
        closing_quote = value.find("'", 1)
        if closing_quote < 0:
            raise EnvironmentFileError(
                f"line {line_number}: unterminated single quote"
            )
        if value[closing_quote + 1 :].strip():
            raise EnvironmentFileError(
                f"line {line_number}: unexpected text after quoted value"
            )
        return value[1:closing_quote]
    if value.startswith('"'):
        return _parse_double_quoted(value, line_number)
    return _parse_unquoted(value, line_number)


def parse_environment_file(path: Path) -> list[tuple[str, str]]:
    raw = path.read_bytes()
    if b"\0" in raw:
        raise EnvironmentFileError("NUL bytes are not allowed")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnvironmentFileError("file must be valid UTF-8") from exc

    assignments: list[tuple[str, str]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if "=" not in line:
            raise EnvironmentFileError(
                f"line {line_number}: expected a variable assignment"
            )
        raw_name, raw_value = line.split("=", 1)
        name = raw_name.strip()
        if VARIABLE_NAME.fullmatch(name) is None:
            raise EnvironmentFileError(
                f"line {line_number}: invalid variable name"
            )
        assignments.append((name, _parse_value(raw_value, line_number)))
    return assignments


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: parse_systemd_env.py ENVIRONMENT_FILE", file=sys.stderr)
        return 2

    path = Path(arguments[0])
    try:
        assignments = parse_environment_file(path)
    except (EnvironmentFileError, OSError) as exc:
        print(f"Unable to parse environment file {path}: {exc}", file=sys.stderr)
        return 1

    output = sys.stdout.buffer
    for name, value in assignments:
        output.write(name.encode("utf-8"))
        output.write(b"=")
        output.write(value.encode("utf-8"))
        output.write(b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
