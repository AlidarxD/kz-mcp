"""The adapter against the real kz-law-retrieval package (BM25 method, tiny corpus).
Skipped when the optional `law` extra is not installed (e.g. in CI)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("kz_law_retrieval")

from mcp import Client

from kz_mcp.retrieval import build_retriever
from kz_mcp.retrieval.kz_law import KzLawRetrieverAdapter
from kz_mcp.server import build_server
from kz_mcp.settings import Settings

FIXTURE = Path(__file__).parents[2] / "src" / "kz_mcp" / "data" / "law_fixture.json"


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """Write the bundled articles as kz-law-llm chunk files (one chunk per article)."""
    chunks = tmp_path / "chunks"
    chunks.mkdir()
    by_file: dict[str, list[str]] = {}
    for a in json.loads(FIXTURE.read_text(encoding="utf-8"))["articles"]:
        chunk = {
            "id": f"{a['code']}:{a['language']}:{a['number']}:0",
            "ngr": a["code"],
            "language": a["language"],
            "law_title": a["law_title"],
            "article_number": a["number"],
            "article_title": a["title"],
            "hierarchy": a["hierarchy"],
            "chunk_index": 0,
            "chunk_count": 1,
            "url": a["url"],
            "text": a["text"],
            "context_header": " › ".join([a["law_title"], *a["hierarchy"], a["heading"]]),
        }
        by_file.setdefault(f"{a['code']}_{a['language']}.jsonl", []).append(json.dumps(chunk))
    for name, lines in by_file.items():
        (chunks / name).write_text("\n".join(lines), encoding="utf-8")
    return tmp_path


def test_adapter_over_real_package(data_dir: Path) -> None:
    adapter = KzLawRetrieverAdapter.from_data_dir(data_dir, method="bm25")
    hits = adapter.search("распитие алкогольных напитков", "ru", None, 3)
    assert hits[0].code == "K1400000235" and hits[0].number == "440"
    assert hits[0].lang == "ru" and hits[0].score is not None
    kk = adapter.search("ұрлық", "kk", "K1400000226", 5)
    assert kk and {h.code for h in kk} == {"K1400000226"}
    article = adapter.get_article("K2500000214", "503", "kk")
    assert article is not None and article.lang == "kk" and article.text
    assert adapter.get_article("K2500000214", "9999", "ru") is None
    assert len(adapter.list_codes()) == 10
    assert [a.number for a in adapter.list_articles("K1500000414", "ru")] == ["77", "88"]


@pytest.mark.anyio
async def test_server_auto_selects_kz_law_backend(data_dir: Path) -> None:
    settings = Settings(law_data_dir=data_dir, law_method="bm25", _env_file=None)
    retriever = build_retriever(settings)
    assert retriever.name == "kz-law-retrieval:bm25"
    async with Client(build_server(settings, retriever)) as client:
        r = await client.call_tool("search_law", {"query": "сверхурочная работа", "code": "labour"})
        out = r.structured_content
        assert out["retriever"] == "kz-law-retrieval:bm25"
        assert out["results"][0]["citation_id"] == "kz-law:K1500000414:ru:77"
