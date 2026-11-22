from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from kz_mcp.models import StrictModel
from kz_mcp.models.common import SourceInfo


class CompanyRecord(StrictModel):
    bin: str
    name_ru: str | None
    name_kk: str | None
    director: str | None = Field(description="Head of the legal entity as registered")
    activity_ru: str | None = Field(description="Main activity (OKED)")
    activity_kk: str | None
    address_ru: str | None
    address_kk: str | None
    status_ru: str | None = Field(description="Registration status, e.g. Зарегистрирован")
    status_kk: str | None
    registered_on: date | None


class CompanyResult(StrictModel):
    bin: str
    entity_type: Literal[
        "resident_legal_entity", "non_resident_legal_entity", "joint_entrepreneurship"
    ] = Field(description="Derived from the 5th digit of the BIN")
    found: bool
    records: list[CompanyRecord] = Field(
        description="Registry records for this BIN; several records mean re-registrations "
        "or changed details, listed as published"
    )
    source: SourceInfo
    notice: str
