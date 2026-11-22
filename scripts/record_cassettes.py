"""Record real upstream responses for integration tests and the offline snapshots.

    python scripts/record_cassettes.py

Cassettes (tests/integration/cassettes) are replayed in tests; snapshots
(src/kz_mcp/snapshots) ship with the package and are served when an upstream is down and
nothing is cached. Each file stores the request it answers, so a replay can check it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CASSETTES = ROOT / "tests" / "integration" / "cassettes"
SNAPSHOTS = ROOT / "src" / "kz_mcp" / "snapshots"

NBK = "https://nationalbank.kz/rss/get_rates.cfm"
EGOV = "https://data.egov.kz/api/detailed/gbd_ul/v1"


def egov_source(bin_: str) -> str:
    return json.dumps({"size": 10, "query": {"term": {"bin": bin_}}}, separators=(",", ":"))


REQUESTS = {
    "nbk_2026-11-20": (NBK, {"fdate": "20.11.2026"}),
    "nbk_2026-12-01_empty": (NBK, {"fdate": "01.12.2026"}),
    "egov_gbd_ul_000740000728": (EGOV, {"source": egov_source("000740000728")}),
    "egov_gbd_ul_990140000007_empty": (EGOV, {"source": egov_source("990140000007")}),
}
SNAPSHOT_OF = {
    "nbk_2026-11-20": "nbk_rates.json",
    "egov_gbd_ul_000740000728": "egov_gbd_ul.json",
}


def main() -> None:
    CASSETTES.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=30, headers={"User-Agent": "kz-mcp-recorder"}) as client:
        for name, (url, params) in REQUESTS.items():
            resp = client.get(url, params=params)
            resp.raise_for_status()
            record = {
                "request": {"method": "GET", "url": url, "params": params},
                "response": {
                    "status": resp.status_code,
                    "content_type": resp.headers.get("content-type", ""),
                    "body": resp.text,
                },
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            text = json.dumps(record, ensure_ascii=False, indent=1) + "\n"
            (CASSETTES / f"{name}.json").write_text(text, encoding="utf-8")
            if name in SNAPSHOT_OF:
                (SNAPSHOTS / SNAPSHOT_OF[name]).write_text(text, encoding="utf-8")
            print(f"{name}: {resp.status_code}, {len(resp.content)} bytes")


if __name__ == "__main__":
    main()
