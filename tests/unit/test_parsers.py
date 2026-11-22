from datetime import date
from decimal import Decimal

import pytest

from kz_mcp.upstream.egov import parse_companies, query_params
from kz_mcp.upstream.nbk import parse_rates
from tests.cassettes import load


def test_parse_nbk_feed():
    day = parse_rates(load("nbk_2026-11-20")["response"]["body"])
    assert day.date == date(2026, 11, 20)
    assert len(day.rates) >= 30
    usd = next(r for r in day.rates if r.code == "USD")
    assert usd.rate > 0 and usd.quant == 1 and usd.direction in {"up", "down", "unchanged", None}
    assert all(len(r.code) == 3 and r.quant >= 1 for r in day.rates)


def test_parse_nbk_empty_day():
    day = parse_rates(load("nbk_2026-12-01_empty")["response"]["body"])
    assert day.date == date(2026, 12, 1) and day.rates == []


@pytest.mark.parametrize(
    "body", ["<html>down</html>", "not xml", "<rates><date>bad</date></rates>"]
)
def test_parse_nbk_malformed(body):
    with pytest.raises(ValueError):  # noqa: PT011
        parse_rates(body)


def test_nbk_parser_rejects_entity_expansion():
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]><rates><date>&b;</date></rates>'
    )
    with pytest.raises(Exception):  # noqa: B017, PT011 - defusedxml refuses entities
        parse_rates(bomb)


def test_nbk_item_details():
    xml = (
        "<rates><date>01.02.2026</date>"
        "<item><fullname>ЙЕНА</fullname><title>jpy</title><description>350.5</description>"
        "<quant>100</quant><index></index><change>0.00</change></item>"
        "<item><title>BAD</title><description>n/a</description></item>"
        "</rates>"
    )
    [jpy] = parse_rates(xml).rates
    assert jpy.code == "JPY" and jpy.quant == 100 and jpy.rate == Decimal("350.5")
    assert jpy.direction == "unchanged"


def test_parse_companies_dedupes_and_filters_bin():
    records = parse_companies(load("egov_gbd_ul_000740000728")["response"]["body"], "000740000728")
    assert records and all(r.bin == "000740000728" for r in records)
    assert records[0].name_ru and records[0].registered_on == date(2000, 7, 2)
    assert len({tuple(vars(r).values()) for r in records}) == len(records)


def test_parse_companies_empty_and_malformed():
    assert parse_companies('{"data":[],"totalCount":0}', "990140000007") == []
    with pytest.raises(ValueError):  # noqa: PT011
        parse_companies('{"error":"x"}', "990140000007")
    other = '{"data":[{"bin":"111111111111","nameru":"X"}]}'
    assert parse_companies(other, "000740000728") == []


def test_egov_query_is_an_exact_term_match():
    assert query_params("000740000728") == {
        "source": '{"size":10,"query":{"term":{"bin":"000740000728"}}}'
    }
