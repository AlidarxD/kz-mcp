"""`company_by_bin`: legal-entity lookup in the public registry (data.egov.kz)."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from kz_mcp.models.company import CompanyRecord, CompanyResult
from kz_mcp.services import Services
from kz_mcp.tools.rates import REMOTE_READ_ONLY, source_info
from kz_mcp.upstream import egov
from kz_mcp.upstream.fetch import UpstreamUnavailableError
from kz_mcp.validation.bin import InvalidBinError, validate_bin

DESCRIPTION = (
    "Look up a legal entity of Kazakhstan by its 12-digit BIN (business identification "
    "number) in the State Database of Legal Entities, published as open data on "
    "data.egov.kz: names (RU/KK), director, main activity, address, status, registration "
    "date. The BIN checksum is validated first. Individuals (IIN) are not supported."
)
NOTICE = (
    "Open-data export of the State Database of Legal Entities (data.egov.kz, dataset gbd_ul); "
    "it can lag the live registry. Verify on egov.kz before relying on it."
)


def register(server: MCPServer, services: Services) -> None:
    @server.tool(
        title="Company lookup by BIN",
        description=DESCRIPTION,
        annotations=REMOTE_READ_ONLY,
    )
    async def company_by_bin(
        bin: Annotated[
            str,
            Field(
                min_length=12,
                max_length=16,
                pattern=r"^[0-9][0-9 -]{10,14}[0-9]$",
                description="12-digit BIN; spaces and dashes are ignored",
            ),
        ],
    ) -> CompanyResult:
        try:
            number, entity_type = validate_bin(bin)
        except InvalidBinError as exc:
            raise ToolError(str(exc)) from None
        s = services.settings
        try:
            records, fetched = await egov.fetch_company(
                services.upstream, number, ttl_s=s.company_ttl_s, stale_ttl_s=s.stale_ttl_s
            )
        except UpstreamUnavailableError:
            raise ToolError(
                "The legal-entity registry (data.egov.kz) is temporarily unavailable; "
                "try again later"
            ) from None
        notice = NOTICE
        if fetched.status in ("stale", "snapshot"):
            notice += (
                f" The registry could not be reached: this is a {fetched.status} copy fetched "
                f"{fetched.fetched_at:%Y-%m-%d %H:%M} UTC."
            )
        return CompanyResult(
            bin=number,
            entity_type=entity_type,
            found=bool(records),
            records=[CompanyRecord(**vars(r)) for r in records],
            source=source_info("data.egov.kz — State Database of Legal Entities", fetched),
            notice=notice,
        )
