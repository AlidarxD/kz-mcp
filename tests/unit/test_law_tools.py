import json

import pytest
from mcp import Client

pytestmark = pytest.mark.anyio


async def test_search_law_returns_structured_hits(client: Client):
    r = await client.call_tool("search_law", {"query": "сверхурочная работа", "top_k": 2})
    assert not r.is_error
    out = r.structured_content
    assert out["retriever"] == "fixture" and out["lang"] == "ru" and out["code"] is None
    top = out["results"][0]
    assert top["citation_id"] == "kz-law:K1500000414:ru:77"
    assert top["code_alias"] == "labour"
    assert top["url"].startswith("https://adilet.zan.kz/rus/docs/K1500000414")
    assert len(top["snippet"]) <= 402
    assert len(out["results"]) <= 2


async def test_search_law_code_filter_accepts_alias(client: Client):
    r = await client.call_tool("search_law", {"query": "ұрлық", "lang": "kk", "code": "criminal"})
    out = r.structured_content
    assert out["code"] == "K1400000226"
    assert {h["code"] for h in out["results"]} == {"K1400000226"}


async def test_search_law_no_results_is_not_an_error(client: Client):
    r = await client.call_tool("search_law", {"query": "qwertyuiop"})
    assert not r.is_error and r.structured_content["results"] == []


@pytest.mark.parametrize(
    "args",
    [
        {"query": "x"},  # too short
        {"query": "a" * 501},
        {"query": "отпуск", "lang": "en"},
        {"query": "отпуск", "top_k": 0},
        {"query": "отпуск", "top_k": 21},
        {"query": "отпуск", "code": "family"},
        {"query": "отпуск", "unexpected": True},
    ],
)
async def test_search_law_rejects_invalid_input(client: Client, args):
    r = await client.call_tool("search_law", args)
    assert r.is_error
    assert "Traceback" not in r.content[0].text


async def test_get_law_article_full_text_and_citation(client: Client):
    r = await client.call_tool(
        "get_law_article", {"code": "K2500000214", "article_number": "503", "lang": "kk"}
    )
    assert not r.is_error
    art = r.structured_content
    assert art["citation_id"] == "kz-law:K2500000214:kk:503"
    assert art["lang"] == "kk" and art["code_alias"] == "tax"
    assert len(art["text"]) > 1000 and art["hierarchy"]
    assert "adilet.zan.kz" in art["source"]


async def test_get_law_article_missing_is_a_helpful_tool_error(client: Client):
    r = await client.call_tool("get_law_article", {"code": "labour", "article_number": "9999"})
    assert r.is_error
    assert "9999" in r.content[0].text and "search_law" in r.content[0].text


@pytest.mark.parametrize("number", ["88; DROP", "../1", "", "1" * 21])
async def test_get_law_article_validates_article_number(client: Client, number):
    r = await client.call_tool("get_law_article", {"code": "labour", "article_number": number})
    assert r.is_error


async def test_resources_list_codes_and_contents(client: Client):
    codes = json.loads((await client.read_resource("kzlaw://codes")).contents[0].text)
    assert {"code", "alias", "lang", "title", "articles", "name_en"} <= set(codes[0])
    toc = json.loads((await client.read_resource("kzlaw://codes/labour/ru")).contents[0].text)
    assert toc["code"] == "K1500000414"
    assert [a["number"] for a in toc["articles"]] == ["77", "88"]
    assert toc["articles"][1]["citation_id"] == "kz-law:K1500000414:ru:88"


@pytest.mark.parametrize("uri", ["kzlaw://codes/family/ru", "kzlaw://codes/labour/en"])
async def test_resource_rejects_bad_params(client: Client, uri):
    with pytest.raises(Exception):  # noqa: B017, PT011 - surfaced as an MCP protocol error
        await client.read_resource(uri)


async def test_prompts(client: Client):
    names = {p.name for p in (await client.list_prompts()).prompts}
    assert names == {"explain_article", "legal_question", "compare_languages"}
    p = await client.get_prompt("explain_article", {"code": "labour", "article_number": "88"})
    text = p.messages[0].content.text
    assert "get_law_article" in text and "citation_id" in text
