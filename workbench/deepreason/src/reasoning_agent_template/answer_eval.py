"""Offline answer probe: evidence availability and literal concept coverage.

This is intentionally a diagnostic, not a semantic entailment or accuracy judge.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def score_case(case: Mapping[str, Any], result: Mapping[str, Any], model_calls: list[str]) -> dict[str, Any]:
    """Attribute an outcome to retrieval, release, or answer wording on a fixed rubric."""
    decision = result["learning"]["decision"]
    release = result["output_release"]["status"]
    qualified = set(result["evidence"]["qualified_evidence_ids"])
    chunks = [chunk for chunk in result["rag"]["results"]
              if chunk["evidence_id"] in qualified]
    anchors = case.get("source_anchors", [])
    anchor_hits = [any(
        Path(chunk["source"]).name == anchor["file"]
        and anchor["contains"] in chunk["text"]
        for chunk in chunks
    ) for anchor in anchors]

    answer = result["answer"]
    facet_hits = [any(phrase in answer for phrase in facet["any_of"])
                  for facet in case.get("answer_facets", [])]
    expected = case["expected_decision"]
    decision_match = decision == expected
    if expected == "answered":
        # The proxy is deliberately strict about missing terms but can miss
        # paraphrases and can accept factually reversed sentences.
        proxy_pass = decision_match and all(anchor_hits) and all(facet_hits)
        failure_layer = (
            "decision" if not decision_match else
            "qualified_evidence" if not all(anchor_hits) else
            "answer_wording" if not all(facet_hits) else "none"
        )
    elif expected == "review_withheld":
        proxy_pass = decision_match and release == "withheld" and "worker" in model_calls and all(anchor_hits)
        failure_layer = "none" if proxy_pass else "review_boundary"
    else:
        proxy_pass = decision_match and "worker" not in model_calls
        failure_layer = "none" if proxy_pass else "stop_boundary"
    return {
        "case": case["id"],
        "expected_decision": expected,
        "observed_decision": decision,
        "release": release,
        "decision_match": decision_match,
        "qualified_anchor_hits": anchor_hits,
        "answer_facet_hits": facet_hits,
        "answer_facet_ids": [facet["id"] for facet in case.get("answer_facets", [])],
        "proxy_pass": proxy_pass,
        "failure_layer": failure_layer,
        "model_calls": model_calls,
        "answer": answer,
    }
