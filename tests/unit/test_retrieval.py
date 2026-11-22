from pathlib import Path
from types import SimpleNamespace

import pytest

from kz_mcp.retrieval import FixtureRetriever, LawRetriever, build_retriever
from kz_mcp.retrieval.kz_law import KzLawRetrieverAdapter
from kz_mcp.settings import Settings


def test_fixture_search_respects_language_and_code():
    r = FixtureRetriever()
    assert isinstance(r, LawRetriever)
    ru = r.search("продолжительность ежегодного отпуска", "ru", None, 3)
    assert ru[0].code == "K1500000414" and ru[0].number == "88"
    assert all(a.lang == "ru" for a in ru)
    assert ru[0].score is not None and ru[0].score > 0
    kk = r.search("еңбек демалысы", "kk", None, 5)
    assert kk and all(a.lang == "kk" for a in kk)
    assert all(a.code == "K1400000226" for a in r.search("кража", "ru", "K1400000226", 5))
    assert r.search("xyzzy", "ru", None, 5) == []


def test_fixture_lookup_and_listing():
    r = FixtureRetriever()
    art = r.get_article("K2500000214", "503", "ru")
    assert art is not None and "налог" in art.text.lower()
    assert r.get_article("K2500000214", "503", "ru") == art
    assert r.get_article("K2500000214", "1", "ru") is None
    codes = {(c.code, c.lang) for c in r.list_codes()}
    assert ("K1500000414", "kk") in codes and len(codes) == 10
    assert [a.number for a in r.list_articles("K1500000414", "ru")] == ["77", "88"]


def _pkg_article(**kw):
    base = dict(
        code="K1",
        number="1",
        language="kaz",
        law_title="Law",
        title="T",
        heading="1-бап. T",
        hierarchy=["Ch"],
        url="https://adilet.zan.kz/kaz/docs/K1",
        text="txt",
        score=0.5,
    )
    return SimpleNamespace(**(base | kw))


class _FakePkgRetriever:
    def __init__(self):
        self.calls = []
        self.searcher = object()

    def search(self, query, lang, code=None, top_k=5):
        self.calls.append((query, lang, code, top_k))
        return [_pkg_article()]

    def get_article(self, code, number, lang):
        return _pkg_article(score=None) if number == "1" else None

    def articles(self, code, lang):
        return [_pkg_article(score=None)]

    def codes(self):
        return [SimpleNamespace(code="K1", language="rus", title="Law", articles=3)]


def test_kz_law_adapter_maps_package_types():
    fake = _FakePkgRetriever()
    adapter = KzLawRetrieverAdapter(fake, "hybrid+rerank")
    assert isinstance(adapter, LawRetriever)
    assert adapter.name == "kz-law-retrieval:hybrid+rerank"
    [hit] = adapter.search("q", "kk", "K1", 3)
    assert fake.calls == [("q", "kk", "K1", 3)]
    assert hit.lang == "kk" and hit.hierarchy == ("Ch",) and hit.score == 0.5
    assert adapter.get_article("K1", "1", "kk").score is None
    assert adapter.get_article("K1", "2", "kk") is None
    assert len(adapter.list_articles("K1", "kk")) == 1
    assert adapter.list_codes()[0].lang == "ru"
    adapter.warmup()


def test_build_retriever_falls_back_to_fixture(tmp_path: Path):
    s = Settings(retriever="auto", law_data_dir=tmp_path, _env_file=None)
    assert build_retriever(s).name == "fixture"
    s = Settings(retriever="fixture", _env_file=None)
    assert build_retriever(s).name == "fixture"


def test_build_retriever_strict_mode_fails_loudly(tmp_path: Path):
    s = Settings(retriever="kz-law", law_data_dir=tmp_path, _env_file=None)
    with pytest.raises(RuntimeError, match="kz-law"):
        build_retriever(s)
