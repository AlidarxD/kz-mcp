import pytest

from kz_mcp.codes import CODES, UnknownCodeError, citation_id, code_by_ngr, resolve_code


def test_resolve_alias_and_ngr():
    assert resolve_code("labour").ngr == "K1500000414"
    assert resolve_code("K1500000414").alias == "labour"
    assert code_by_ngr("nope") is None


def test_unknown_code_lists_valid_aliases():
    with pytest.raises(UnknownCodeError, match="labour"):
        resolve_code("family")


def test_citation_id_is_stable():
    assert citation_id("K1500000414", "ru", "88") == "kz-law:K1500000414:ru:88"


def test_urls_per_language():
    tax = resolve_code("tax")
    assert tax.url("ru") == "https://adilet.zan.kz/rus/docs/K2500000214"
    assert tax.url("kk") == "https://adilet.zan.kz/kaz/docs/K2500000214"
    assert len({c.alias for c in CODES}) == len(CODES)
