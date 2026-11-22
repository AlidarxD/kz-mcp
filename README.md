# kz-mcp

An [MCP](https://modelcontextprotocol.io) server that gives any MCP client (Claude Desktop,
Claude Code, Cursor, …) access to Kazakhstan public data:

- **Legislation**: hybrid search over the Constitution and the Civil, Labour, Tax, Criminal and
  Administrative Offences codes, in Russian and Kazakh, with stable citation ids
- **Exchange rates**: official National Bank of Kazakhstan rates *(M2)*
- **Legal entities**: lookup by BIN in the public registry *(M2)*

The server makes **no LLM calls**: every tool is deterministic code or a local model, and the
client's LLM does the reasoning. Targets MCP spec **2026-07-28** (Python SDK `mcp` 2.x).

> Work in progress — see [docs/PLAN.md](docs/PLAN.md) for milestones.

## Quickstart

```bash
uv venv -p 3.12 && uv pip install -e ".[dev]"
kz-mcp                      # stdio server, bundled demo corpus
```

With the full legal index from [kz-law-llm](https://github.com/AlidarXD/kz-law-llm)
(private for now; expects a checkout next to this repo):

```bash
uv pip install -e ".[law]"
KZ_MCP_LAW_DATA_DIR=../kz-law-llm/data kz-mcp
```

### Claude Code

```bash
claude mcp add kz-mcp -- uv --directory /path/to/kz-mcp run kz-mcp
```

## Tools

| Tool | Description |
|---|---|
| `search_law(query, lang, code?, top_k)` | articles answering a question: code, article number, heading, snippet, adilet.zan.kz link, citation id |
| `get_law_article(code, article_number, lang)` | full current text of one article with a stable citation id |

Resources: `kzlaw://codes`, `kzlaw://codes/{code}/{lang}`. Prompts: `explain_article`,
`legal_question`, `compare_languages`.

## Configuration

Environment variables (prefix `KZ_MCP_`), see [.env.example](.env.example).

## Development

```bash
pytest --cov            # unit, contract, e2e
ruff check . && mypy
UPDATE_SNAPSHOTS=1 pytest tests/contract   # accept an intentional schema change
```

*Not legal advice. Always check the linked article on adilet.zan.kz.*
