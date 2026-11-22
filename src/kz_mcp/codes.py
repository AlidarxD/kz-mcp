"""The legal acts the server knows about, with short aliases for tool arguments."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

Lang = Literal["ru", "kk"]


@dataclass(frozen=True)
class LawCode:
    ngr: str  # document code on adilet.zan.kz
    alias: str
    name_en: str

    def url(self, lang: Lang) -> str:
        section = "rus" if lang == "ru" else "kaz"
        return f"https://adilet.zan.kz/{section}/docs/{self.ngr}"


CODES: tuple[LawCode, ...] = (
    LawCode("K2600000000", "constitution", "Constitution of the Republic of Kazakhstan"),
    LawCode("K940001000_", "civil-general", "Civil Code (General Part)"),
    LawCode("K990000409_", "civil-special", "Civil Code (Special Part)"),
    LawCode("K1500000414", "labour", "Labour Code"),
    LawCode("K1400000235", "administrative", "Code of Administrative Offences"),
    LawCode("K1400000226", "criminal", "Criminal Code"),
    LawCode("K2500000214", "tax", "Tax Code"),
)

# Static enum for strict tool schemas: aliases and Adilet codes are both accepted.
CodeName = Literal[
    "constitution",
    "civil-general",
    "civil-special",
    "labour",
    "administrative",
    "criminal",
    "tax",
    "K2600000000",
    "K940001000_",
    "K990000409_",
    "K1500000414",
    "K1400000235",
    "K1400000226",
    "K2500000214",
]

_BY_NAME: dict[str, LawCode] = {c.alias: c for c in CODES} | {c.ngr: c for c in CODES}


class UnknownCodeError(ValueError):
    pass


def resolve_code(name: str) -> LawCode:
    try:
        return _BY_NAME[name]
    except KeyError:
        valid = ", ".join(c.alias for c in CODES)
        raise UnknownCodeError(f"Unknown law code {name!r}. Valid codes: {valid}") from None


def code_by_ngr(ngr: str) -> LawCode | None:
    return _BY_NAME.get(ngr)


def citation_id(ngr: str, lang: Lang, article_number: str) -> str:
    """Stable, human-readable citation id, e.g. `kz-law:K1500000414:ru:88`."""
    return f"kz-law:{ngr}:{lang}:{article_number}"


assert set(get_args(CodeName)) == set(_BY_NAME), "CodeName out of sync with CODES"  # noqa: S101
