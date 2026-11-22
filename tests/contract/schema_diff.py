"""Classify differences between two tool-schema snapshots as breaking or not."""

from __future__ import annotations

from typing import Any

Schema = dict[str, Any]


def _resolve(schema: Schema, root: Schema) -> Schema:
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/$defs/"):
        return root.get("$defs", {}).get(ref.split("/")[-1], schema)  # type: ignore[no-any-return]
    return schema


def _types(schema: Schema) -> set[str]:
    if "anyOf" in schema:
        return set().union(*(_types(s) for s in schema["anyOf"]))
    t = schema.get("type")
    return set(t) if isinstance(t, list) else {t} if t else {"any"}


def _enum(schema: Schema) -> set[Any] | None:
    if "enum" in schema:
        return set(schema["enum"])
    if "anyOf" in schema:
        values: set[Any] = set()
        for s in schema["anyOf"]:
            e = _enum(s)
            if e is None:
                if s.get("type") == "null":
                    values.add(None)
                    continue
                return None
            values |= e
        return values
    return None


def _diff_object(
    old: Schema, new: Schema, root_old: Schema, root_new: Schema, path: str, is_input: bool
) -> list[str]:
    problems: list[str] = []
    old, new = _resolve(old, root_old), _resolve(new, root_new)
    old_props, new_props = old.get("properties", {}), new.get("properties", {})
    old_req, new_req = set(old.get("required", [])), set(new.get("required", []))
    for name, old_prop in old_props.items():
        if name not in new_props:
            problems.append(f"{path}.{name}: removed")
            continue
        new_prop = new_props[name]
        o, n = _resolve(old_prop, root_old), _resolve(new_prop, root_new)
        if is_input and not _types(n) >= _types(o):
            problems.append(f"{path}.{name}: type narrowed {_types(o)} -> {_types(n)}")
        if not is_input and not _types(n) <= _types(o):
            problems.append(f"{path}.{name}: type widened {_types(o)} -> {_types(n)}")
        oe, ne = _enum(o), _enum(n)
        if is_input and oe is not None and ne is not None and oe - ne:
            problems.append(f"{path}.{name}: enum values removed {sorted(map(str, oe - ne))}")
        if "properties" in o or "properties" in n:
            problems += _diff_object(o, n, root_old, root_new, f"{path}.{name}", is_input)
        if o.get("type") == "array" and "items" in o and "items" in n:
            problems += _diff_object(
                o["items"], n["items"], root_old, root_new, f"{path}.{name}[]", is_input
            )
    if is_input:
        problems += [f"{path}.{name}: newly required" for name in sorted(new_req - old_req)]
        if (
            old.get("additionalProperties", True) is not False
            and new.get("additionalProperties", True) is False
            and path == "input"
        ):
            problems.append(f"{path}: additionalProperties now false")
    else:
        problems += [f"{path}.{name}: no longer required" for name in sorted(old_req - new_req)]
    return problems


def breaking_changes(old: dict[str, Schema], new: dict[str, Schema]) -> list[str]:
    """`old`/`new` map tool name -> {"inputSchema": …, "outputSchema": …}."""
    problems = [f"tool {name}: removed" for name in sorted(set(old) - set(new))]
    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        problems += [
            f"tool {name}: {p}"
            for p in _diff_object(
                o["inputSchema"],
                n["inputSchema"],
                o["inputSchema"],
                n["inputSchema"],
                "input",
                is_input=True,
            )
        ]
        if o.get("outputSchema"):
            if not n.get("outputSchema"):
                problems.append(f"tool {name}: outputSchema removed")
            else:
                problems += [
                    f"tool {name}: {p}"
                    for p in _diff_object(
                        o["outputSchema"],
                        n["outputSchema"],
                        o["outputSchema"],
                        n["outputSchema"],
                        "output",
                        is_input=False,
                    )
                ]
    return problems
