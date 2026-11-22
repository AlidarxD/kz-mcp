# kz-mcp — implementation plan

An MCP server that exposes Kazakhstan public data — legislation, National Bank exchange rates,
the legal-entity registry and data.egov.kz open data — to any MCP client. The server makes no
LLM calls: every tool is deterministic code or a local model; the client's LLM does the reasoning.

## Target protocol and SDK

| | Version | Notes |
|---|---|---|
| MCP specification | **2026-07-28** (latest published revision) | stateless requests with version/capabilities in `_meta`, `server/discover`, HTTP+SSE transport deprecated, OpenTelemetry trace-context keys in `_meta` (SEP-414) |
| Backward compatibility | 2025-11-25 and earlier, negotiated by the SDK | Claude Desktop / Cursor builds that still speak the legacy handshake keep working |
| Python SDK | `mcp` **2.3.0** (2026-10-02) | `mcp.server.mcpserver.MCPServer` (ex-FastMCP), `ToolAnnotations`, structured output from Pydantic return types, `TokenVerifier` + `AuthSettings` for the resource-server role, `mcp.Client` for in-process and HTTP e2e tests. SDK reports `LATEST_PROTOCOL_VERSION = "2026-07-28"` |
| Python | 3.12 | |

Transports: **stdio** and **Streamable HTTP** (stateless mode, which is what 2026-07-28 is built
around and what lets the HTTP server scale behind a plain load balancer). HTTP+SSE is not
offered — it is deprecated in the target spec.

Auth (HTTP only): OAuth 2.1 **resource server** per the MCP authorization spec — bearer tokens
validated by a pluggable `TokenVerifier` (JWT/JWKS or RFC 7662 introspection), RFC 9728
protected-resource metadata pointing at an external authorization server, audience
(resource indicator, RFC 8707) checks. A static-token verifier for local development.
The server never issues tokens itself.

## Upstream endpoints (verified 2026-11-22)

| Source | Endpoint | Result | Decision |
|---|---|---|---|
| Legislation | local index built by `kz-law-llm` (Adilet JSON API → BM25 + e5 ONNX + Qdrant + bge-reranker) | works offline | reused via the `kz_law_retrieval` package behind an adapter |
| National Bank rates | `GET https://nationalbank.kz/rss/get_rates.cfm?fdate=DD.MM.YYYY` | **200**, XML, all currencies with `quant`, change, date | used for `exchange_rates` |
| Legal-entity registry (stat.gov.kz) | `GET https://old.stat.gov.kz/api/juridical/counter/api/?bin=…` | **403 Forbidden** (blocked for non-browser clients); the new `stat.gov.kz` path returns 404 | **not used** |
| Legal-entity registry (alternative) | `GET https://data.egov.kz/api/detailed/gbd_ul/v1?source={…}` — dataset "Регистрационные данные юридических лиц" (ГБД ЮЛ), Elasticsearch-style query, no API key | **200**, JSON: BIN, RU/KZ name, director, OKED, RU/KZ address, status, registration date; ~1M records | used for `company_by_bin`. Caveat: open-data export, not a real-time registry; a BIN can have several records (re-registrations) |
| data.egov.kz API v4 | `GET https://data.egov.kz/api/v4/<dataset>/<ver>?apiKey=…` | **403 "API key is invalid"** — needs a registered account | not used (requires an account) |
| data.egov.kz dataset rows | `GET https://data.egov.kz/api/detailed/<dataset>/<ver>?source={…}` | **200** without a key | usable for `open_data_get` |
| data.egov.kz metadata | `GET https://data.egov.kz/meta/<dataset>/<ver>` | **200**, JSON (names, keywords, fields) | usable for `open_data_get` schema / validation |
| data.egov.kz catalogue search | `/datasets/search?text=…` | HTML only, no JSON API found | `open_data_search` will search a locally built catalogue (metadata of a curated dataset list refreshed from `/meta`), not scrape HTML. Decided in M3+ |

Every upstream call: httpx timeout, tenacity retry with exponential backoff + jitter on
network errors / 5xx / 429, Redis cache with per-source TTL, and an **offline snapshot fallback**
(recorded responses shipped with the package) used when the upstream is down and in tests.

## Repository structure

```
kz-mcp/
├── pyproject.toml              # hatchling, uv; entry point `kz-mcp`
├── src/kz_mcp/
│   ├── __main__.py / cli.py    # `kz-mcp [--transport stdio|http]`
│   ├── server.py               # builds MCPServer: tools, resources, prompts
│   ├── settings.py             # pydantic-settings, prefix KZ_MCP_
│   ├── errors.py               # safe client-facing errors (no stack traces)
│   ├── models/                 # strict Pydantic input/output models per tool
│   ├── tools/                  # law.py, rates.py, company.py, opendata.py
│   ├── resources.py            # law codes as MCP resources
│   ├── prompts.py              # explain-article-with-citations, …
│   ├── retrieval/              # LawRetriever protocol + adapters
│   │   ├── base.py             # protocol: search(), get_article(), list_codes()
│   │   ├── kz_law.py           # adapter over kz_law_retrieval (optional extra `law`)
│   │   └── fixture.py          # small in-memory corpus (tests, demo without index)
│   ├── upstream/
│   │   ├── http.py             # shared httpx client, timeouts, retry/backoff
│   │   ├── cache.py            # Redis cache (TTL, hit/miss counters), in-memory fallback
│   │   ├── snapshots.py        # offline fallback loader
│   │   ├── nbk.py              # National Bank rates (XML)
│   │   └── egov.py             # data.egov.kz (gbd_ul, detailed, meta)
│   ├── validation/bin.py       # BIN/IIN format + checksum
│   └── snapshots/              # recorded upstream responses (package data)
├── tests/
│   ├── unit/ contract/ integration/ e2e/
│   └── contract/schemas/       # snapshotted tool input/output JSON schemas
├── docs/  PLAN.md  ARCHITECTURE.md  adr/
├── deploy/  Dockerfile  docker-compose.yml  prometheus/  grafana/   (M3–M4)
├── loadtest/                   (M4)
└── .github/workflows/ci.yml  .pre-commit-config.yaml  .env.example
```

Index files, models and `data/` are never committed (`.gitignore`).

## Tools

| Tool | Annotations | Upstream |
|---|---|---|
| `search_law(query, lang: ru\|kk, code?, top_k)` | readOnly, idempotent, closedWorld | local index |
| `get_law_article(code, article_number, lang)` → full text + stable citation id `kz:<ngr>:<lang>:art<N>` | readOnly, idempotent, closedWorld | local index |
| `exchange_rates(date?, currencies?)` | readOnly, idempotent, openWorld | NBK |
| `company_by_bin(bin)` — checksum validated before any request | readOnly, idempotent, openWorld | data.egov.kz gbd_ul |
| `open_data_search(query)` / `open_data_get(dataset_id, filters)` | readOnly, idempotent, openWorld | data.egov.kz |

Resources: `kzlaw://codes` (list) and `kzlaw://codes/{code}/{lang}` (table of contents).
Prompts: `explain_article`, `compare_ru_kk`, `company_due_diligence`.

## Milestones

| | Scope | Done when |
|---|---|---|
| **M1** | skeleton, settings, stdio transport, retrieval adapter (kz_law_retrieval + fixture), `search_law`, `get_law_article`, law resources, prompts, schema contract tests, e2e over stdio, CI (ruff, mypy --strict, pytest) | tests green, pushed |
| **M2** | upstream HTTP layer (timeouts, retry/backoff), Redis cache + in-memory fallback, offline snapshots, `exchange_rates`, `company_by_bin` with BIN checksum, recorded-response integration tests | tests green, pushed |
| M3 | Streamable HTTP, OAuth 2.1 resource server + static-token mode, Redis per-client rate limiting, request size limits, open-data tools | |
| M4 | JSON logs, OpenTelemetry per tool call, Prometheus metrics, compose with Prometheus + Grafana + dashboard, load test | |
| M5 | `uvx kz-mcp` packaging, PyPI / MCP registry metadata, Docker, README client snippets, ARCHITECTURE, ADRs, Limitations | |

## Dependency on kz-law-llm

`kz-law-llm` is private, so `kz_law_retrieval` is wired as a **local path** dependency
(`[tool.uv.sources]`) under the optional extra `law` for now. CI and the default install do not
need it: the server falls back to the fixture retriever and says so in `search_law` metadata.
Once `kz-law-llm` is public the source switches to a git subdirectory URL.
