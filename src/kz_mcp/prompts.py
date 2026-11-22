"""Reusable prompts that steer the client's LLM to ground answers in the tools."""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

DISCLAIMER = "Finish with one line saying this is not legal advice."


def register(server: MCPServer) -> None:
    @server.prompt(
        title="Explain an article with citations",
        description="Explain one article of a Kazakhstan code in plain language, citing it",
    )
    def explain_article(code: str, article_number: str, lang: str = "ru") -> str:
        return (
            f"Call get_law_article with code={code!r}, article_number={article_number!r}, "
            f"lang={lang!r}. Explain the article in plain language in the same language as "
            "the article: who it applies to, what it requires or allows, deadlines, amounts "
            "and exceptions. Use only the article text. Quote the key sentence and cite it as "
            f"[citation_id](url). {DISCLAIMER}"
        )

    @server.prompt(
        title="Answer a legal question from the law",
        description="Answer a question about Kazakhstan law using only retrieved articles",
    )
    def legal_question(question: str, lang: str = "ru") -> str:
        return (
            f"Question: {question}\n\n"
            f"Call search_law with this question and lang={lang!r}. If a snippet is not "
            "enough, call get_law_article for the full text. Answer only from the returned "
            "articles; every statement must cite an article as [citation_id](url). If the "
            "articles do not answer the question, say so plainly instead of answering from "
            f"memory: the law changes and the retrieved text is current. {DISCLAIMER}"
        )

    @server.prompt(
        title="Compare Russian and Kazakh texts",
        description="Compare the Russian and Kazakh editions of one article",
    )
    def compare_languages(code: str, article_number: str) -> str:
        return (
            f"Call get_law_article for code={code!r}, article_number={article_number!r} twice, "
            "with lang='ru' and lang='kk'. Compare the two editions point by point and list "
            "any difference in meaning, numbers, deadlines or scope. Report differences "
            "without deciding which edition prevails. Cite both citation ids."
        )
