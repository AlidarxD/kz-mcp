"""Contract tests: the public surface (tools, prompts, resources) is snapshotted as JSON.

Any change fails until the snapshot is regenerated with UPDATE_SNAPSHOTS=1. Breaking changes
(removed tools or fields, narrowed input types, new required inputs, …) are refused even then,
unless ALLOW_BREAKING=1 is set as well: they need a major version bump.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from tests.contract.schema_diff import breaking_changes

pytestmark = pytest.mark.anyio

SNAPSHOTS = Path(__file__).parent / "schemas"
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"
ALLOW_BREAKING = os.environ.get("ALLOW_BREAKING") == "1"


def _dump(obj: Any) -> Any:
    return obj.model_dump(mode="json", by_alias=True, exclude_none=True)


def _check(name: str, current: Any) -> None:
    path = SNAPSHOTS / f"{name}.json"
    text = json.dumps(current, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if not path.exists() or UPDATE:
        path.write_text(text, encoding="utf-8")
        return
    assert path.read_text(encoding="utf-8") == text, (
        f"{path.name} changed; review the diff and run UPDATE_SNAPSHOTS=1 pytest tests/contract"
    )


async def test_tool_schemas(client: Client) -> None:
    tools = (await client.list_tools()).tools
    current = {
        t.name: {
            k: v
            for k, v in _dump(t).items()
            if k in {"name", "title", "description", "inputSchema", "outputSchema", "annotations"}
        }
        for t in tools
    }
    for name, schema in current.items():
        path = SNAPSHOTS / f"tool.{name}.json"
        if path.exists():
            old = {name: json.loads(path.read_text(encoding="utf-8"))}
            problems = breaking_changes(old, {name: schema})
            assert not problems or ALLOW_BREAKING, f"breaking changes: {problems}"
        _check(f"tool.{name}", schema)
    known = {p.name[len("tool.") : -len(".json")] for p in SNAPSHOTS.glob("tool.*.json")}
    removed = known - set(current)
    assert not removed or ALLOW_BREAKING, f"breaking changes: tools removed {sorted(removed)}"


async def test_every_tool_is_annotated_and_structured(client: Client) -> None:
    for tool in (await client.list_tools()).tools:
        a = tool.annotations
        assert a is not None, tool.name
        assert a.read_only_hint is not None and a.idempotent_hint is not None, tool.name
        assert a.open_world_hint is not None and a.destructive_hint is not None, tool.name
        assert tool.output_schema is not None, f"{tool.name} has no outputSchema"
        assert tool.input_schema.get("additionalProperties") is False, tool.name


async def test_prompt_and_resource_surface(client: Client) -> None:
    prompts = sorted(
        (_dump(p) for p in (await client.list_prompts()).prompts), key=lambda p: p["name"]
    )
    resources = [_dump(r) for r in (await client.list_resources()).resources]
    templates = [_dump(t) for t in (await client.list_resource_templates()).resource_templates]
    _check("prompts", prompts)
    _check("resources", {"resources": resources, "templates": templates})
