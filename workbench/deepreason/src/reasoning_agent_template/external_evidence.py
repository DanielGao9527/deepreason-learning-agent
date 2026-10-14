from __future__ import annotations

import html as html_lib
import json
import re
from typing import Any, Callable
from urllib import error, parse, request

from reasoning_agent_template.evidence import EvidenceLedger
from reasoning_agent_template.models import KnowledgeChunk, stable_hash


SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
CROSSREF_URL = "https://api.crossref.org/works"
DUCKDUCKGO_URL = "https://api.duckduckgo.com/"
MIN_EXTERNAL_RELEVANCE = 0.08

QUERY_EXPANSIONS = {
    "高熵合金": "high entropy alloys",
    "强度": "strength",
    "影响因素": "factors",
    "机理": "mechanism",
    "机制": "mechanism",
    "强化机制": "strengthening mechanism",
    "力学性能": "mechanical properties",
    "微观组织": "microstructure",
    "相结构": "phase structure",
    "相组成": "phase composition",
    "固溶强化": "solid solution strengthening",
    "析出强化": "precipitation strengthening",
    "晶粒": "grain size",
    "位错": "dislocation",
    "热处理": "heat treatment",
    "退火": "annealing",
    "冷加工": "cold working",
    "材料科学": "materials science",
    "金属材料": "metallic materials",
    "企业知识库": "enterprise knowledge base",
    "知识库": "knowledge base",
    "向量数据库": "vector database",
    "选型": "selection",
    "依据": "evidence",
    "来源": "sources",
    "状态机": "state machine",
    "多 agent": "multi-agent",
    "多Agent": "multi-agent",
    "智能体": "agent",
    "工作流": "workflow",
    "长短期记忆": "short-term long-term memory",
    "长期记忆": "long-term memory",
    "短期记忆": "short-term memory",
}


class ExternalEvidenceSearch:
    """Network-backed evidence search for papers and user-provided experience."""

    def __init__(
        self,
        *,
        ledger: EvidenceLedger,
        timeout_seconds: int = 8,
        urlopen: Callable[..., Any] | None = None,
    ):
        self.ledger = ledger
        self.timeout_seconds = timeout_seconds
        self.urlopen = urlopen or request.urlopen
        self.diagnostics: list[dict[str, Any]] = []

    def retrieve(self, query: str, *, top_k: int = 5, sources: list[str] | None = None) -> list[KnowledgeChunk]:
        requested = set(sources or [])
        buckets: list[list[KnowledgeChunk]] = []

        if "user_experience" in requested:
            buckets.append(self._user_experience(query))

        if "papers" in requested:
            paper_query = _paper_query(query)
            paper_results = self._semantic_scholar(paper_query, top_k=max(1, top_k))
            if len(paper_results) < top_k:
                paper_results.extend(self._crossref(paper_query, top_k=top_k - len(paper_results)))
            if not paper_results:
                self._diagnose("papers", "empty", f"no paper evidence returned for query: {paper_query}")
            buckets.append(paper_results)

        if "web" in requested:
            web_results = self._web_search(query, top_k=max(1, top_k))
            if not web_results:
                self._diagnose("web", "empty", f"no web evidence returned for query: {_external_query(query)}")
            buckets.append(web_results)

        return _balanced_dedupe(buckets, top_k=top_k)

    def _web_search(self, query: str, *, top_k: int) -> list[KnowledgeChunk]:
        search_query = _external_query(query)
        params = {
            "q": search_query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        data = self._get_json(f"{DUCKDUCKGO_URL}?{parse.urlencode(params)}", provider="duckduckgo_api")
        if not isinstance(data, dict):
            return []

        candidates: list[tuple[str, str, str]] = []
        abstract = _clean_text(_first_text(data.get("AbstractText")))
        abstract_url = _first_text(data.get("AbstractURL"))
        heading = _first_text(data.get("Heading")) or "DuckDuckGo result"
        if abstract and abstract_url:
            candidates.append((heading, abstract_url, abstract))

        for topic in _flatten_related_topics(data.get("RelatedTopics")):
            text = _clean_text(_first_text(topic.get("Text")))
            url = _first_text(topic.get("FirstURL"))
            if text and url:
                candidates.append((_summarize(text, limit=80), url, text))

        if not candidates:
            candidates.extend(self._duckduckgo_html(search_query, top_k=top_k))
        if not candidates:
            candidates.extend(self._official_docs_fallback(search_query, top_k=top_k))

        results: list[KnowledgeChunk] = []
        filtered = 0
        for index, (title, uri, text) in enumerate(candidates[:top_k], start=1):
            content = _join_parts([f"Title: {title}", f"URL: {uri}", f"Snippet: {text}"])
            if _relevance(search_query, content) < MIN_EXTERNAL_RELEVANCE:
                filtered += 1
                continue
            evidence = self.ledger.record(
                source_type="web",
                uri=uri,
                locator=f"DuckDuckGo result {index}",
                content=content,
                summary=_summarize(content),
                confidence=0.68,
                used_for=["external:web"],
            )
            results.append(
                KnowledgeChunk(
                    source=uri,
                    span=evidence.locator,
                    text=content,
                    content_hash=stable_hash(content),
                    score=evidence.confidence,
                    evidence_id=evidence.id,
                )
            )
        if candidates and not results:
            self._diagnose("web", "filtered", f"{filtered or len(candidates)} web candidate(s) failed relevance filtering")
        return results

    def _duckduckgo_html(self, query: str, *, top_k: int) -> list[tuple[str, str, str]]:
        params = {"q": query}
        text = self._get_text(f"https://duckduckgo.com/html/?{parse.urlencode(params)}", provider="duckduckgo_html")
        if not text:
            return []
        links = re.findall(
            r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet_matches = re.findall(
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>|'
            r'<div[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</div>',
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        flat_snippets = [_strip_tags((match[0] or match[1])) for match in snippet_matches]
        candidates: list[tuple[str, str, str]] = []
        for index, (raw_url, raw_title) in enumerate(links[:top_k]):
            uri = _normalize_duckduckgo_url(html_lib.unescape(raw_url))
            title = _strip_tags(html_lib.unescape(raw_title))
            snippet = flat_snippets[index] if index < len(flat_snippets) else ""
            if uri and title:
                candidates.append((title, uri, snippet or title))
        return candidates

    def _official_docs_fallback(self, query: str, *, top_k: int) -> list[tuple[str, str, str]]:
        candidates: list[tuple[str, str, str]] = []
        for title, uri, trigger_terms in _official_doc_sources():
            if len(candidates) >= top_k:
                break
            lowered = query.lower()
            if not any(term in lowered for term in trigger_terms):
                continue
            text = self._get_text(uri, provider=f"official_docs:{title}")
            extracted = _extract_page_summary(text)
            if extracted:
                candidates.append((title, uri, extracted))
        if candidates:
            self._diagnose("web", "fallback", f"official docs fallback returned {len(candidates)} candidate(s)")
        return candidates

    def _semantic_scholar(self, query: str, *, top_k: int) -> list[KnowledgeChunk]:
        params = {
            "query": query,
            "limit": str(max(1, top_k)),
            "fields": "title,abstract,year,url,authors,citationCount,venue",
        }
        data = self._get_json(f"{SEMANTIC_SCHOLAR_URL}?{parse.urlencode(params)}", provider="semantic_scholar")
        rows = data.get("data", []) if isinstance(data, dict) else []
        results: list[KnowledgeChunk] = []
        filtered = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _first_text(row.get("title"))
            if not title:
                continue
            paper_id = _first_text(row.get("paperId")) or stable_hash(title)[:12]
            abstract = _clean_text(_first_text(row.get("abstract")))
            year = _first_text(row.get("year"))
            venue = _first_text(row.get("venue"))
            authors = ", ".join(
                _first_text(author.get("name"))
                for author in row.get("authors", [])
                if isinstance(author, dict) and _first_text(author.get("name"))
            )
            citation_count = _first_text(row.get("citationCount")) or "0"
            uri = _first_text(row.get("url")) or f"https://www.semanticscholar.org/paper/{paper_id}"
            text = _join_parts(
                [
                    f"Title: {title}",
                    f"Year: {year}" if year else "",
                    f"Venue: {venue}" if venue else "",
                    f"Authors: {authors}" if authors else "",
                    f"Citations: {citation_count}",
                    f"Abstract: {abstract}" if abstract else "",
                ]
            )
            if _relevance(query, text) < MIN_EXTERNAL_RELEVANCE:
                filtered += 1
                continue
            evidence = self.ledger.record(
                source_type="paper",
                uri=uri,
                locator=f"Semantic Scholar paperId={paper_id}",
                content=text,
                summary=_summarize(text),
                confidence=_paper_confidence(row.get("citationCount")),
                used_for=["external:semantic_scholar"],
            )
            results.append(
                KnowledgeChunk(
                    source=uri,
                    span=evidence.locator,
                    text=text,
                    content_hash=stable_hash(text),
                    score=evidence.confidence,
                    evidence_id=evidence.id,
                )
            )
        if rows and not results:
            self._diagnose("semantic_scholar", "filtered", f"{filtered or len(rows)} paper candidate(s) failed relevance filtering")
        return results

    def _crossref(self, query: str, *, top_k: int) -> list[KnowledgeChunk]:
        params = {
            "query.bibliographic": query,
            "rows": str(max(1, top_k)),
            "select": "DOI,title,abstract,published-print,published-online,container-title,URL,author,is-referenced-by-count",
        }
        data = self._get_json(f"{CROSSREF_URL}?{parse.urlencode(params)}", provider="crossref")
        rows = (((data or {}).get("message") or {}).get("items") or []) if isinstance(data, dict) else []
        results: list[KnowledgeChunk] = []
        filtered = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            title = _first_text(row.get("title"))
            if not title:
                continue
            doi = _first_text(row.get("DOI"))
            uri = _first_text(row.get("URL")) or (f"https://doi.org/{doi}" if doi else f"https://api.crossref.org/works/{stable_hash(title)[:12]}")
            year = _crossref_year(row)
            journal = _first_text(row.get("container-title"))
            abstract = _strip_tags(_first_text(row.get("abstract")))
            authors = _crossref_authors(row.get("author"))
            citation_count = _first_text(row.get("is-referenced-by-count")) or "0"
            text = _join_parts(
                [
                    f"Title: {title}",
                    f"Year: {year}" if year else "",
                    f"Journal: {journal}" if journal else "",
                    f"Authors: {authors}" if authors else "",
                    f"Citations: {citation_count}",
                    f"DOI: {doi}" if doi else "",
                    f"Abstract: {abstract}" if abstract else "",
                ]
            )
            if _relevance(query, text) < MIN_EXTERNAL_RELEVANCE:
                filtered += 1
                continue
            evidence = self.ledger.record(
                source_type="paper",
                uri=uri,
                locator=f"Crossref DOI={doi or 'unknown'}",
                content=text,
                summary=_summarize(text),
                confidence=_paper_confidence(row.get("is-referenced-by-count")),
                used_for=["external:crossref"],
            )
            results.append(
                KnowledgeChunk(
                    source=uri,
                    span=evidence.locator,
                    text=text,
                    content_hash=stable_hash(text),
                    score=evidence.confidence,
                    evidence_id=evidence.id,
                )
            )
        if rows and not results:
            self._diagnose("crossref", "filtered", f"{filtered or len(rows)} paper candidate(s) failed relevance filtering")
        return results

    def _user_experience(self, query: str) -> list[KnowledgeChunk]:
        markers = ["我的经验", "我的观察", "我发现", "我们项目", "我们团队", "根据我的", "our experience", "i observed"]
        if not any(marker in query.lower() for marker in markers):
            return []
        content = _clean_text(query)
        evidence = self.ledger.record(
            source_type="user_experience",
            uri="user://current-message",
            locator="prompt",
            content=content,
            summary=_summarize(content),
            confidence=0.65,
            used_for=["external:user_experience"],
        )
        return [
            KnowledgeChunk(
                source=evidence.uri,
                span=evidence.locator,
                text=content,
                content_hash=evidence.content_hash,
                score=evidence.confidence,
                evidence_id=evidence.id,
            )
        ]

    def _get_json(self, url: str, *, provider: str) -> dict[str, Any]:
        req = request.Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "reasoning-agent-template/0.1",
            },
            method="GET",
        )
        try:
            with self.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            self._diagnose(provider, "error", f"HTTP {exc.code} {exc.reason}", url=url)
            return {}
        except (OSError, error.URLError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            self._diagnose(provider, "error", f"{type(exc).__name__}: {exc}", url=url)
            return {}

    def _get_text(self, url: str, *, provider: str) -> str:
        req = request.Request(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "User-Agent": "reasoning-agent-template/0.1",
            },
            method="GET",
        )
        try:
            with self.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            self._diagnose(provider, "error", f"HTTP {exc.code} {exc.reason}", url=url)
            return ""
        except (OSError, error.URLError, TypeError, AttributeError) as exc:
            self._diagnose(provider, "error", f"{type(exc).__name__}: {exc}", url=url)
            return ""

    def _diagnose(self, source: str, status: str, message: str, *, url: str | None = None) -> None:
        item = {"source": source, "status": status, "message": message}
        if url:
            item["url"] = url
        self.diagnostics.append(item)


def _paper_query(query: str) -> str:
    text = query.strip()
    mappings = {
        "大语言模型": "large language models",
        "大型语言模型": "large language models",
        "医学诊断": "medical diagnosis",
        "医疗诊断": "medical diagnosis",
        "临床诊断": "clinical diagnosis",
        "诊断": "diagnosis",
        "临床": "clinical",
        "最新研究": "recent research",
        "研究进展": "research progress",
        "综述": "review",
        "论文": "papers",
        "文献": "literature",
        "关键论文": "key papers",
        "人工智能": "artificial intelligence",
    }
    mappings.update(QUERY_EXPANSIONS)
    additions = [english for chinese, english in mappings.items() if chinese in text]
    if additions:
        return " ".join(dict.fromkeys(additions))
    return re.sub(r"\s+", " ", text)


def _external_query(query: str) -> str:
    text = re.sub(r"\s+", " ", query.strip())
    lowered = text.lower()
    additions = [english for source, english in QUERY_EXPANSIONS.items() if source.lower() in lowered]
    if not additions:
        return text
    return " ".join(dict.fromkeys([*additions, text]))


def _flatten_related_topics(value: Any) -> list[dict[str, Any]]:
    topics: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return topics
    for item in value:
        if not isinstance(item, dict):
            continue
        if "Topics" in item:
            topics.extend(_flatten_related_topics(item.get("Topics")))
        else:
            topics.append(item)
    return topics


def _normalize_duckduckgo_url(value: str) -> str:
    if value.startswith("//"):
        value = "https:" + value
    parsed = parse.urlparse(value)
    query = parse.parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return query["uddg"][0]
    return value


def _dedupe(results: list[KnowledgeChunk]) -> list[KnowledgeChunk]:
    seen: set[str] = set()
    unique: list[KnowledgeChunk] = []
    for result in results:
        key = result.evidence_id or result.content_hash
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def _balanced_dedupe(buckets: list[list[KnowledgeChunk]], *, top_k: int) -> list[KnowledgeChunk]:
    selected: list[KnowledgeChunk] = []
    seen: set[str] = set()

    def add(result: KnowledgeChunk) -> None:
        key = result.evidence_id or result.content_hash
        if key in seen or len(selected) >= top_k:
            return
        seen.add(key)
        selected.append(result)

    for bucket in buckets:
        if bucket:
            add(bucket[0])
    for bucket in buckets:
        for result in bucket[1:]:
            add(result)
            if len(selected) >= top_k:
                break
        if len(selected) >= top_k:
            break
    return selected


def _relevance(query: str, text: str) -> float:
    query_terms = _evidence_terms(query)
    text_terms = _evidence_terms(text)
    if "vector" in query_terms and "database" in query_terms and "vector" not in text_terms:
        return 0.0
    english_query_terms = {term for term in query_terms if re.search(r"[a-z]", term)}
    if english_query_terms:
        query_terms = english_query_terms
    if not query_terms:
        return 0.0
    return len(query_terms.intersection(text_terms)) / len(query_terms)


def _evidence_terms(value: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]+", value.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            terms.update(token)
            terms.update(token[index : index + 2] for index in range(max(0, len(token) - 1)))
        elif len(token) > 2:
            terms.add(token)
    return terms


def _first_text(value: Any) -> str:
    if isinstance(value, list):
        return _first_text(value[0]) if value else ""
    if value is None:
        return ""
    return str(value).strip()


def _clean_text(value: str) -> str:
    return " ".join(str(value).split())


def _join_parts(parts: list[str]) -> str:
    return "\n".join(part for part in parts if part)


def _summarize(value: str, limit: int = 220) -> str:
    collapsed = _clean_text(value)
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def _paper_confidence(citation_count: Any) -> float:
    try:
        citations = int(citation_count or 0)
    except (TypeError, ValueError):
        citations = 0
    return min(0.95, 0.72 + min(citations, 100) / 500)


def _strip_tags(value: str) -> str:
    return _clean_text(re.sub(r"<[^>]+>", " ", value))


def _crossref_year(row: dict[str, Any]) -> str:
    for key in ("published-print", "published-online"):
        parts = ((row.get(key) or {}).get("date-parts") or [])
        if parts and parts[0]:
            return _first_text(parts[0][0])
    return ""


def _crossref_authors(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    names = []
    for author in value[:8]:
        if not isinstance(author, dict):
            continue
        given = _first_text(author.get("given"))
        family = _first_text(author.get("family"))
        name = " ".join(part for part in [given, family] if part)
        if name:
            names.append(name)
    return ", ".join(names)


def _official_doc_sources() -> list[tuple[str, str, list[str]]]:
    return [
        (
            "LangChain RAG documentation",
            "https://python.langchain.com/docs/tutorials/rag/",
            ["rag", "retrieval", "augmented", "generation"],
        ),
        (
            "Chroma documentation",
            "https://docs.trychroma.com/docs/overview/introduction",
            ["chroma"],
        ),
        (
            "Milvus documentation",
            "https://milvus.io/docs/overview.md",
            ["milvus"],
        ),
        (
            "LangGraph overview",
            "https://docs.langchain.com/oss/python/langgraph/overview",
            ["langgraph"],
        ),
        (
            "CrewAI documentation",
            "https://docs.crewai.com/",
            ["crewai"],
        ),
    ]


def _extract_page_summary(text: str) -> str:
    if not text:
        return ""
    title = ""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if title_match:
        title = _strip_tags(html_lib.unescape(title_match.group(1)))
    meta = ""
    meta_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if meta_match:
        meta = _strip_tags(html_lib.unescape(meta_match.group(1)))
    body = _strip_tags(text)[:600]
    return _summarize(_join_parts([title, meta, body]), limit=500)
