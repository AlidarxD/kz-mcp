"""A small in-memory retriever over a bundled subset of real articles.

Used by tests, CI and as a zero-setup demo when the kz-law-llm index is not installed. Scoring
is a plain TF-IDF over 5-character prefixes, which is enough for the dozen bundled articles;
it is not meant to be a good search engine.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from importlib import resources
from pathlib import Path
from typing import Any

from kz_mcp.codes import Lang
from kz_mcp.retrieval.base import IndexedCode, RetrievedArticle

_WORD = re.compile(r"\w+", re.UNICODE)
_PREFIX = 5
_LANG = {"rus": "ru", "kaz": "kk"}


def _tokens(text: str) -> list[str]:
    return [w[:_PREFIX] for w in _WORD.findall(text.lower().replace("ё", "е")) if len(w) > 2]


def _load(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        raw = resources.files("kz_mcp.data").joinpath("law_fixture.json").read_text("utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    articles: list[dict[str, Any]] = json.loads(raw)["articles"]
    return articles


class FixtureRetriever:
    name = "fixture"

    def __init__(self, path: Path | None = None) -> None:
        self._articles = [
            RetrievedArticle(
                code=a["code"],
                number=a["number"],
                lang=_LANG[a["language"]],  # type: ignore[arg-type]
                law_title=a["law_title"],
                title=a.get("title", ""),
                heading=a["heading"],
                url=a["url"],
                text=a["text"],
                hierarchy=tuple(a.get("hierarchy", ())),
            )
            for a in _load(path)
        ]
        self._tf = [Counter(_tokens(f"{a.heading}\n{a.text}")) for a in self._articles]
        df: Counter[str] = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(self._articles)
        self._idf = {t: math.log(1 + n / d) for t, d in df.items()}

    def search(
        self, query: str, lang: Lang, code: str | None, top_k: int
    ) -> list[RetrievedArticle]:
        terms = _tokens(query)
        scored = []
        for article, tf in zip(self._articles, self._tf, strict=True):
            if article.lang != lang or (code is not None and article.code != code):
                continue
            score = sum(self._idf.get(t, 0.0) * math.log1p(tf[t]) for t in terms)
            if score > 0:
                scored.append((score, article))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [_with_score(a, s) for s, a in scored[:top_k]]

    def get_article(self, code: str, number: str, lang: Lang) -> RetrievedArticle | None:
        return next(
            (a for a in self._articles if a.code == code and a.number == number and a.lang == lang),
            None,
        )

    def list_articles(self, code: str, lang: Lang) -> list[RetrievedArticle]:
        return [a for a in self._articles if a.code == code and a.lang == lang]

    def list_codes(self) -> list[IndexedCode]:
        counts: Counter[tuple[str, Lang]] = Counter((a.code, a.lang) for a in self._articles)
        titles = {(a.code, a.lang): a.law_title for a in self._articles}
        return [
            IndexedCode(code=c, lang=lang, title=titles[(c, lang)], articles=n)
            for (c, lang), n in sorted(counts.items())
        ]


def _with_score(article: RetrievedArticle, score: float) -> RetrievedArticle:
    from dataclasses import replace

    return replace(article, score=round(score, 4))
