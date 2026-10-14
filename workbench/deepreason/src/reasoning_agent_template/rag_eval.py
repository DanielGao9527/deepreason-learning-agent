from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from reasoning_agent_template.knowledge import LocalKnowledgeBase


DEFAULT_METHOD_SETS: dict[str, list[str]] = {
    "keyword": ["keyword"],
    "bm25": ["bm25"],
    "semantic": ["semantic"],
    "graph": ["graph"],
    "hybrid": ["bm25", "semantic", "graph"],
}
DEFAULT_TOP_KS = [1, 3, 5]


@dataclass(frozen=True)
class RagEvalCase:
    id: str
    query: str
    expected_sources: list[str]
    tags: list[str]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RagEvalCase":
        expected_sources = data.get("expected_sources")
        if not isinstance(expected_sources, list):
            expected_sources = [data["expected_source"]]
        return cls(
            id=str(data["id"]),
            query=str(data["query"]),
            expected_sources=[str(item) for item in expected_sources],
            tags=[str(item) for item in data.get("tags", [])],
        )


def load_cases(path: Path) -> list[RagEvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("cases", raw) if isinstance(raw, dict) else raw
    return [RagEvalCase.from_dict(dict(row)) for row in rows]


def evaluate_knowledge_base(
    *,
    knowledge_dir: Path,
    cases: list[RagEvalCase],
    method_sets: dict[str, list[str]] | None = None,
    top_ks: list[int] | None = None,
    min_score: float = 0.0,
    max_chunk_chars: int = 1400,
) -> dict[str, Any]:
    methods = method_sets or DEFAULT_METHOD_SETS
    k_values = sorted(set(top_ks or DEFAULT_TOP_KS))
    kb = LocalKnowledgeBase(knowledge_dir, max_chunk_chars=max_chunk_chars)
    chunks = kb.ingest()
    payload: dict[str, Any] = {
        "knowledge_dir": str(knowledge_dir),
        "index": {
            "chunk_count": len(chunks),
            "source_count": len({str(chunk.source) for chunk in chunks}),
            "max_chunk_chars": max_chunk_chars,
        },
        "case_count": len(cases),
        "top_ks": k_values,
        "min_score": min_score,
        "methods": {},
    }

    for label, selected_methods in methods.items():
        rows = []
        hits_by_k = {k: 0 for k in k_values}
        for case in cases:
            results = kb.retrieve(
                case.query,
                top_k=max(k_values),
                methods=selected_methods,
                min_score=min_score,
            )
            sources = [Path(result.source).as_posix() for result in results]
            ranks = [
                index + 1
                for index, source in enumerate(sources)
                if any(
                    _source_matches(source=source, expected=expected_source)
                    for expected_source in case.expected_sources
                )
            ]
            rank = ranks[0] if ranks else None
            for k in k_values:
                if rank is not None and rank <= k:
                    hits_by_k[k] += 1
            rows.append(
                {
                    "id": case.id,
                    "query": case.query,
                    "expected_sources": list(case.expected_sources),
                    "rank": rank,
                    "top_sources": sources,
                    "top_methods": [result.retrieval_method for result in results],
                    "top_scores": [round(result.score, 6) for result in results],
                    "score_breakdowns": [result.score_breakdown for result in results],
                    "tags": list(case.tags),
                }
            )
        payload["methods"][label] = {
            "selected_methods": selected_methods,
            "recall": {
                f"recall@{k}": round(hits_by_k[k] / max(1, len(cases)), 4)
                for k in k_values
            },
            "hits": {f"@{k}": hits_by_k[k] for k in k_values},
            "misses": [
                row
                for row in rows
                if row["rank"] is None or row["rank"] > max(k_values)
            ],
            "cases": rows,
        }
    return payload


def format_markdown_report(payload: dict[str, Any]) -> str:
    lines = [
        "# RAG Benchmark Report",
        "",
        f"- Knowledge directory: `{payload['knowledge_dir']}`",
        f"- Sources: `{payload['index']['source_count']}`",
        f"- Chunks: `{payload['index']['chunk_count']}`",
        f"- Cases: `{payload['case_count']}`",
        f"- Min score: `{payload['min_score']}`",
        "",
        "## Recall",
        "",
        "| Method | Recall@1 | Recall@3 | Recall@5 | Misses |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, result in payload["methods"].items():
        recall = result["recall"]
        lines.append(
            "| "
            + " | ".join(
                [
                    label,
                    _percent(recall.get("recall@1", 0.0)),
                    _percent(recall.get("recall@3", 0.0)),
                    _percent(recall.get("recall@5", 0.0)),
                    str(len(result["misses"])),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Misses", ""])
    any_miss = False
    for label, result in payload["methods"].items():
        if not result["misses"]:
            continue
        any_miss = True
        lines.append(f"### {label}")
        lines.append("")
        for miss in result["misses"]:
            top = ", ".join(miss["top_sources"][:3]) or "no hits"
            expected = ", ".join(f"`{source}`" for source in miss["expected_sources"])
            lines.append(
                f"- `{miss['id']}` expected one of {expected}, top results: {top}"
            )
        lines.append("")
    if not any_miss:
        lines.append("No misses at the largest evaluated K.")
        lines.append("")
    lines.extend(
        [
            "## Index Initialization Notes",
            "",
            "The local index is initialized by `LocalKnowledgeBase.ingest()`: recurse supported files, split them into size-bounded chunks, attach source path, line span and content hash, then build method-specific scoring structures at query time.",
            "",
            "- `keyword`: exact lexical overlap over normalized terms.",
            "- `bm25`: per-query BM25-style scoring over expanded terms.",
            "- `semantic`: deterministic term/synonym/trigram vector similarity.",
            "- `graph`: local term co-occurrence graph built from the current chunk set, then query expansion through neighboring terms.",
            "- `hybrid`: weighted merge of BM25, semantic and graph scores.",
            "- `wiki`: external fallback source, not part of the local index.",
            "",
        ]
    )
    return "\n".join(lines)


def _source_matches(*, source: str, expected: str) -> bool:
    normalized_source = source.replace("\\", "/")
    normalized_expected = expected.replace("\\", "/")
    return normalized_source.endswith(normalized_expected) or normalized_expected in normalized_source


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"
