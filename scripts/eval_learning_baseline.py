"""Reproduce local retrieval and evidence qualification without an LLM call.

This is a diagnostic baseline, not a model-answer accuracy evaluation. Human
labels in learning_questions_v1.json identify which source passages would be
needed; the script checks where those passages disappear from the pipeline.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench" / "deepreason"
KNOWLEDGE = WORKBENCH / "evals" / "corpus_v1"
CASES = WORKBENCH / "evals" / "learning_questions_v1.json"
DEFAULT_OUTPUT = ROOT / "artifacts" / "analysis" / "learning_v1_baseline_2026-09-29.json"
sys.path.insert(0, str(WORKBENCH / "src"))

from reasoning_agent_template.knowledge import LocalKnowledgeBase  # noqa: E402
from reasoning_agent_template.learning import (  # noqa: E402
    _explicit_comparison_subjects,
    learning_config,
)
from reasoning_agent_template.workflow import TemplateCoordinator  # noqa: E402


FIXED_ROUTE = {
    "difficulty": "simple",
    "workflow": "evidence_soft",
    "evidence_mode": "required",
    "evidence_strictness": "soft",
    "risk_level": "medium",
    "category": "technical_claim",
    "sources": ["rag"],
    "confidence": 1.0,
    "source": "offline_fixed_route_no_model",
}
EXPERIMENTAL_ALIASES = (
    ("二叉搜索树", "binary search tree BST"),
    ("哈希", "hashing hash table"),
    ("精确匹配", "exact-match query"),
)


def expand_experimental_query(question: str) -> str:
    aliases = [english for chinese, english in EXPERIMENTAL_ALIASES if chinese in question]
    return f"{question} {' '.join(aliases)}" if aliases else question


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(knowledge: Path, cases_path: Path, overrides: Path | None = None) -> list[dict[str, Any]]:
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("cases"), list):
        raise ValueError("Unsupported case file")
    cases = data["cases"]
    if overrides is not None:
        changes = json.loads(overrides.read_text(encoding="utf-8"))
        if changes.get("schema_version") != 1 or not isinstance(changes.get("cases"), dict):
            raise ValueError("Unsupported case overrides")
        by_id = {case["id"]: case for case in cases}
        for case_id, fields in changes["cases"].items():
            if case_id not in by_id or not isinstance(fields, dict):
                raise ValueError(f"Unknown or invalid override: {case_id}")
            by_id[case_id].update(fields)
    ids: set[str] = set()
    splits: set[str] = set()
    for case in cases:
        case_id = str(case.get("id", ""))
        if not case_id or case_id in ids:
            raise ValueError(f"Duplicate or missing case id: {case_id!r}")
        ids.add(case_id)
        split = str(case.get("split", ""))
        if split not in {"dev", "holdout"}:
            raise ValueError(f"Invalid split for {case_id}: {split}")
        splits.add(split)
        if not str(case.get("question", "")).strip():
            raise ValueError(f"Question missing for {case_id}")
        expected = case.get("expected")
        anchors = case.get("support")
        if expected not in {"supported", "unsupported"} or not isinstance(anchors, list):
            raise ValueError(f"Invalid support label for {case_id}")
        if expected == "supported" and not anchors:
            raise ValueError(f"Supporting anchors missing for {case_id}")
        if expected == "unsupported" and (anchors or not case.get("absence_reason")):
            raise ValueError(f"Unsupported case needs an absence reason: {case_id}")
        for anchor in anchors:
            filename = str(anchor.get("file", ""))
            excerpt = str(anchor.get("contains", ""))
            if Path(filename).name != filename or not excerpt:
                raise ValueError(f"Invalid support anchor in {case_id}")
            path = knowledge / filename
            if not path.is_file() or excerpt not in path.read_text(encoding="utf-8"):
                raise ValueError(f"Support anchor absent from corpus: {case_id}/{filename}")
    if splits != {"dev", "holdout"}:
        raise ValueError("Both development and holdout cases are required")
    return cases


def matches(anchor: dict[str, str], chunk: Any) -> bool:
    return Path(chunk.source).name == anchor["file"] and anchor["contains"] in chunk.text


def covered(anchors: list[dict[str, str]], chunks: list[Any]) -> bool:
    return all(any(matches(anchor, chunk) for chunk in chunks) for anchor in anchors)


def candidate(chunk: Any) -> dict[str, Any]:
    return {
        "file": Path(chunk.source).name,
        "span": chunk.span,
        "score": round(chunk.score, 6),
        "scores": dict(chunk.score_breakdown),
        "content_hash": chunk.content_hash,
        "excerpt": chunk.text[:180],
    }


def diagnose(case: dict[str, Any], corpus_chunks: list[Any], all_hits: list[Any],
             score_hits: list[Any], selected: list[Any], qualified_ids: set[str]) -> tuple[str, dict[str, bool]]:
    anchors = case["support"]
    stages = {
        "corpus_chunk": covered(anchors, corpus_chunks) if anchors else False,
        "any_score": covered(anchors, all_hits) if anchors else False,
        "min_score": covered(anchors, score_hits) if anchors else False,
        "top_k": covered(anchors, selected) if anchors else False,
        "gate_qualified": covered(anchors, [chunk for chunk in selected if chunk.evidence_id in qualified_ids])
        if anchors else False,
    }
    if case["expected"] == "unsupported":
        return "corpus_missing", stages
    if not stages["corpus_chunk"]:
        return "chunk_boundary_loss", stages
    if not stages["any_score"]:
        return "retrieval_miss", stages
    if not stages["min_score"]:
        return "min_score_filtered", stages
    if not stages["top_k"]:
        return "top_k_ranking_omission", stages
    if not stages["gate_qualified"]:
        return "evidence_qualification_reject", stages
    return "retrieval_and_gate_ready", stages


def evaluate_case(case: dict[str, Any], scratch: Path, knowledge: Path, expand_query: bool) -> dict[str, Any]:
    shutil.copytree(knowledge, scratch / "knowledge")
    config = learning_config(scratch)
    coordinator = TemplateCoordinator(config=config, workspace_root=scratch)
    retrieval_query = expand_experimental_query(case["question"]) if expand_query else case["question"]
    result = coordinator.run(retrieval_query, routing_decision=FIXED_ROUTE)
    state = result.state
    kb = LocalKnowledgeBase(scratch / "knowledge")
    corpus_chunks = kb.ingest()
    methods = list(config.knowledge["retrieval_methods"])
    all_hits = kb.retrieve(retrieval_query, top_k=999, methods=methods, min_score=0.0)
    score_hits = kb.retrieve(retrieval_query, top_k=999, methods=methods,
                             min_score=float(config.knowledge["min_score"]))
    selected = list(state.retrieval_results)
    qualified_ids = set(state.qualified_evidence_ids)
    diagnosis, anchor_stages = diagnose(case, corpus_chunks, all_hits, score_hits, selected, qualified_ids)
    combined_floor = float(config.gates.get("local_evidence_min_score", 0.45))
    semantic_floor = float(config.gates.get("local_evidence_min_semantic_score", 0.25))
    strong_local = [
        chunk for chunk in selected
        if chunk.score >= combined_floor
        and ("semantic" not in chunk.retrieval_method
             or chunk.score_breakdown.get("semantic", 0.0) >= semantic_floor)
    ]
    subjects = _explicit_comparison_subjects(case["question"])
    qualified_text = "\n".join(chunk.text for chunk in selected if chunk.evidence_id in qualified_ids)
    missing_subjects = [subject for subject in subjects or () if subject not in qualified_text]
    gate_status = result.gate_decisions[-1].status if result.gate_decisions else "missing"
    worker_eligible = bool(qualified_ids) and gate_status == "allow" and not missing_subjects
    return {
        "id": case["id"],
        "split": case["split"],
        "question": case["question"],
        "retrieval_query": retrieval_query,
        "human_expected": case["expected"],
        "human_rationale": case["rationale"],
        "absence_reason": case.get("absence_reason"),
        "support_anchors": case["support"],
        "diagnosis": diagnosis,
        "anchor_stage_coverage": anchor_stages,
        "candidate_count_before_min_score": len(all_hits),
        "candidate_count_after_min_score": len(score_hits),
        "selected_count": len(selected),
        "strong_local_chunk_count": len(strong_local),
        "gate_status": gate_status,
        "evidence_status": state.evidence_status,
        "qualified_evidence_count": len(qualified_ids),
        "unsupported_qualification_exposure": case["expected"] == "unsupported" and bool(qualified_ids),
        "explicit_comparison_subjects": list(subjects) if subjects else [],
        "missing_comparison_subjects": missing_subjects,
        "worker_eligible_by_deterministic_checks": worker_eligible,
        "selected": [candidate(chunk) | {"qualified_by_gate": chunk.evidence_id in qualified_ids,
                                         "strong_local": chunk in strong_local} for chunk in selected],
        "all_scored": [candidate(chunk) for chunk in all_hits],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--corpus", type=Path, default=KNOWLEDGE)
    parser.add_argument("--cases", type=Path, default=CASES)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--expand-query", action="store_true", help="Apply experimental bilingual aliases (not wired to the app)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    knowledge = args.corpus.resolve()
    if not knowledge.is_dir():
        parser.error(f"Corpus does not exist: {knowledge}")
    if output.exists() and not args.overwrite:
        parser.error(f"Baseline already exists: {output}; use --overwrite only intentionally")
    cases_path = args.cases.resolve()
    cases = load_cases(knowledge, cases_path, args.overrides.resolve() if args.overrides else None)
    config = learning_config(WORKBENCH / "learning_mvp")
    scratch_parent = ROOT / "artifacts" / "tmp"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="learning-eval-", dir=scratch_parent) as tmp:
            rows.append(evaluate_case(case, Path(tmp), knowledge, args.expand_query))
    report = {
        "purpose": "Offline retrieval and gate-qualification diagnostic; no LLM answer generated",
        "dataset_sha256": sha256(cases_path),
        "corpus_sha256": {path.name: sha256(path) for path in sorted(knowledge.iterdir()) if path.is_file()},
        "code_sha256": {
            name: sha256(WORKBENCH / "src" / "reasoning_agent_template" / name)
            for name in ("knowledge.py", "workflow.py", "learning.py")
        },
        "evaluator_sha256": sha256(Path(__file__)),
        "fixed_route": FIXED_ROUTE,
        "query_expansion_enabled": args.expand_query,
        "retrieval_config": {
            "methods": config.knowledge["retrieval_methods"],
            "top_k": config.knowledge["top_k"],
            "min_score": config.knowledge["min_score"],
            "local_evidence_min_score": config.gates.get("local_evidence_min_score", 0.45),
            "local_evidence_min_semantic_score": config.gates.get("local_evidence_min_semantic_score", 0.25),
        },
        "summary": {
            split: {
                "cases": sum(row["split"] == split for row in rows),
                "human_supported": sum(row["split"] == split and row["human_expected"] == "supported" for row in rows),
                "human_unsupported": sum(row["split"] == split and row["human_expected"] == "unsupported" for row in rows),
                "supported_anchor_in_top_k": sum(
                    row["split"] == split and row["human_expected"] == "supported"
                    and row["anchor_stage_coverage"]["top_k"] for row in rows
                ),
                "supported_anchor_qualified": sum(
                    row["split"] == split and row["human_expected"] == "supported"
                    and row["anchor_stage_coverage"]["gate_qualified"] for row in rows
                ),
                "supported_with_any_qualified_evidence": sum(
                    row["split"] == split and row["human_expected"] == "supported"
                    and row["qualified_evidence_count"] > 0 for row in rows
                ),
                "supported_worker_eligible": sum(
                    row["split"] == split and row["human_expected"] == "supported"
                    and row["worker_eligible_by_deterministic_checks"] for row in rows
                ),
                "worker_eligible_without_annotated_support": sum(
                    row["split"] == split and row["worker_eligible_by_deterministic_checks"]
                    and row["human_expected"] == "supported"
                    and not row["anchor_stage_coverage"]["gate_qualified"] for row in rows
                ),
                "diagnoses": dict(Counter(row["diagnosis"] for row in rows if row["split"] == split)),
                "unsupported_qualification_exposure": sum(row["split"] == split and row["unsupported_qualification_exposure"] for row in rows),
                "unsupported_worker_eligible": sum(
                    row["split"] == split and row["human_expected"] == "unsupported"
                    and row["worker_eligible_by_deterministic_checks"] for row in rows
                ),
            }
            for split in ("dev", "holdout")
        },
        "cases": rows,
        "limitations": [
            "Human labels are a small, manually selected teaching set, not a general accuracy benchmark.",
            "Text anchors prove passage presence only, not that a model answer is semantically supported.",
            "Any qualified evidence is not the same as qualification of the human-annotated supporting passage.",
            "Gate qualification may include weak chunks once any selected local chunk is strong.",
            "The route is fixed to required+soft; routing accuracy, model output, tokens, and live latency are not measured.",
        ],
        "real_qwen_calls": 0,
    }
    if args.overrides:
        report["overrides_sha256"] = sha256(args.overrides.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "summary": report["summary"],
                      "cases": [{"id": row["id"], "diagnosis": row["diagnosis"],
                                 "qualified": row["qualified_evidence_count"]} for row in rows],
                      "real_qwen_calls": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
