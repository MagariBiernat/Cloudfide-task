#!/usr/bin/env python3
"""Validate .agent-report/report.json against the schema and business rules.

Stdlib-only (a small subset of JSON Schema is implemented: type, enum, required,
additionalProperties, properties, items, minLength, maxLength, maxItems, minimum).
Business rules on top of the schema:
  * create/update entries must list test files and be verification.status=passed
  * test files must live in test paths
  * in PR mode every target from changes.json must be reported
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema/report.schema.json"
TEST_PATH = re.compile(r"^(backend/tests/.+\.py|frontend/src/.+\.test\.tsx?|frontend/src/test/.+)$")
TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float),
         "boolean": bool, "null": type(None)}


def _type_ok(value, expected) -> bool:
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        if name in ("integer", "number") and isinstance(value, bool):
            continue
        if isinstance(value, TYPES[name]):
            return True
    return False


def validate_schema(value, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}: {value!r} not in {schema['enum']}"]
    if "type" in schema and not _type_ok(value, schema["type"]):
        return [f"{path}: expected {schema['type']}, got {type(value).__name__}"]
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below minimum {schema['minimum']}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        for i, item in enumerate(value):
            errors += validate_schema(item, schema.get("items", {}), f"{path}[{i}]")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected property '{key}'")
        for key, sub in props.items():
            if key in value:
                errors += validate_schema(value[key], sub, f"{path}.{key}")
    return errors


def validate_rules(report: dict, changes: dict | None) -> list[str]:
    errors: list[str] = []
    for i, f in enumerate(report.get("files", [])):
        where = f"$.files[{i}] ({f.get('source')})"
        decision = f.get("decision")
        status = (f.get("verification") or {}).get("status")
        if decision in ("create", "update"):
            if not f.get("test_files"):
                errors.append(f"{where}: {decision} without test_files")
            if status != "passed":
                errors.append(f"{where}: {decision} must have verification.status=passed (got {status}); "
                              "remove failing tests and report skip/flag_suspected_bug instead")
        for tf in f.get("test_files", []):
            if not TEST_PATH.match(tf):
                errors.append(f"{where}: {tf} is not a test path")
    if changes and report.get("mode") == "pr":
        reported = {f.get("source") for f in report.get("files", [])}
        for t in changes.get("targets", []):
            if t.get("role") in ("source", "docs", "style", "story", "config") and t["path"] not in reported:
                errors.append(f"$.files: missing decision for changed file {t['path']}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--changes", type=Path, help="map_changes.py output, to check completeness")
    args = parser.parse_args(argv)

    try:
        report = json.loads(args.report.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [f"cannot read report: {exc}"]}, indent=2))
        return 1
    changes = json.loads(args.changes.read_text()) if args.changes and args.changes.exists() else None
    errors = validate_schema(report, json.loads(SCHEMA_PATH.read_text())) + validate_rules(report, changes)
    print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
