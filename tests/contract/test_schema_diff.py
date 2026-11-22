from tests.contract.schema_diff import breaking_changes

BASE = {
    "inputSchema": {
        "type": "object",
        "properties": {
            "q": {"type": "string"},
            "lang": {"enum": ["ru", "kk"], "type": "string"},
        },
        "required": ["q"],
    },
    "outputSchema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                    "required": ["id"],
                },
            }
        },
        "required": ["items"],
    },
}


def _clone():
    import copy

    return copy.deepcopy(BASE)


def test_identical_is_not_breaking():
    assert breaking_changes({"t": BASE}, {"t": _clone()}) == []


def test_additive_changes_are_not_breaking():
    new = _clone()
    new["inputSchema"]["properties"]["top_k"] = {"type": "integer"}
    new["outputSchema"]["properties"]["extra"] = {"type": "string"}
    new["inputSchema"]["properties"]["lang"]["enum"].append("en")
    assert breaking_changes({"t": BASE}, {"t": new}) == []


def test_breaking_changes_detected():
    new = _clone()
    new["inputSchema"]["required"].append("lang")
    new["inputSchema"]["properties"]["lang"]["enum"] = ["ru"]
    del new["outputSchema"]["properties"]["items"]["items"]["properties"]["id"]
    problems = breaking_changes({"t": BASE, "gone": BASE}, {"t": new})
    assert "tool gone: removed" in problems
    assert any("newly required" in p for p in problems)
    assert any("enum values removed" in p for p in problems)
    assert any("items[].id: removed" in p for p in problems)


def test_input_type_narrowing_detected():
    new = _clone()
    new["inputSchema"]["properties"]["q"] = {"type": "integer"}
    assert any("type narrowed" in p for p in breaking_changes({"t": BASE}, {"t": new}))
