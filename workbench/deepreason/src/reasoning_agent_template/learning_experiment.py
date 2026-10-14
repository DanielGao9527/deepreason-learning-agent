"""Bounded model accounting and content-bound manual review for paired experiments."""
from __future__ import annotations

import hashlib
import json
import re
from time import perf_counter
from typing import Any

from reasoning_agent_template.llm import LLMRequestError


METRICS = ("correctness", "premises", "citation_support", "appropriate_stop")


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def call_summary(calls: list[dict]) -> dict:
    known = [call["usage"] for call in calls if call.get("usage") is not None]
    complete = len(known) == len(calls)
    return {
        "forwarded_attempts": len(calls),
        "failed_attempts": sum(call["status"] == "failed" for call in calls),
        "usage_complete": complete,
        "prompt_tokens": sum(item["prompt_tokens"] for item in known) if complete else None,
        "completion_tokens": sum(item["completion_tokens"] for item in known) if complete else None,
        "known_usage_attempts": len(known),
        "known_prompt_tokens": sum(item["prompt_tokens"] for item in known),
        "known_completion_tokens": sum(item["completion_tokens"] for item in known),
        "currency_cost": None,
    }


def terminal_model_failures(calls: list[dict]) -> list[str]:
    """A successful retry clears a role failure; a safe fallback does not."""
    last_status = {call["role"]: call["status"] for call in calls}
    return sorted(role for role, status in last_status.items() if status != "succeeded")


class ExperimentClient:
    """Count every forwarded attempt; never persist prompts or provider error bodies."""

    def __init__(self, backend: Any, *, max_calls: int):
        if type(max_calls) is not int or not 1 <= max_calls <= 100:
            raise ValueError("invalid_experiment_call_limit")
        self.backend = backend
        self.model = backend.model
        self.max_calls = max_calls
        self.calls: list[dict] = []
        self.rejected_calls = 0
        self.blocked_reason: str | None = None
        self.returned_model: str | None = None

    def chat(self, messages, *, temperature, max_tokens):
        if self.backend.model != self.model:
            self.blocked_reason = "requested_model_changed"
        if self.blocked_reason or len(self.calls) >= self.max_calls:
            self.rejected_calls += 1
            self.blocked_reason = self.blocked_reason or "experiment_call_limit"
            raise LLMRequestError("experiment_stopped", retryable=False)
        system = messages[0].content if messages else ""
        request = next((message.content for message in messages if message.role == "user"), "")
        if request.startswith("ROUTING_DECISION_JSON schema:"):
            role = "route"
        elif request.startswith("REVIEW_DECISION_JSON schema:"):
            role = "reviewer"
        elif system.startswith("You are an independent final-answer reviewer.") and "OUTPUT_REVIEW_JSON" in system:
            role = "output_reviewer"
        else:
            role = "worker"
        record = {
            "attempt": len(self.calls) + 1, "role": role,
            "requested_model": _model_label(self.model),
            "temperature": temperature, "max_tokens": max_tokens,
            "prompt_sha256": content_hash([message.to_dict() for message in messages]),
            "skill_loaded": role == "worker" and "已审批教学 Skill" in system,
            "status": "started", "usage": None,
        }
        self.calls.append(record)
        started = perf_counter()
        try:
            result = self.backend.chat(messages, temperature=temperature, max_tokens=max_tokens)
            record["status"] = "succeeded"
            record["returned_model"] = _model_label(result.model)
            raw_usage = result.raw.get("usage") if isinstance(result.raw, dict) else None
            if isinstance(raw_usage, dict) and all(
                type(raw_usage.get(key)) is int and raw_usage[key] >= 0
                for key in ("prompt_tokens", "completion_tokens")
            ):
                record["usage"] = {key: raw_usage[key] for key in ("prompt_tokens", "completion_tokens")}
            if record["returned_model"] == "unknown" or (
                self.returned_model is not None and record["returned_model"] != self.returned_model
            ):
                self.blocked_reason = "returned_model_changed_or_unknown"
                raise LLMRequestError("experiment_model_identity_changed", retryable=False)
            self.returned_model = record["returned_model"]
            return result
        except Exception as exc:
            record["status"] = "failed"
            record["error_type"] = type(exc).__name__
            retryable = isinstance(exc, LLMRequestError) and exc.retryable
            record["retryable"] = retryable
            if isinstance(exc, LLMRequestError) and type(exc.status_code) is int:
                record["http_status"] = exc.status_code
            if not retryable:
                self.blocked_reason = self.blocked_reason or "non_retryable_backend_failure"
            raise
        finally:
            record["duration_ms"] = round((perf_counter() - started) * 1000, 2)


def _model_label(value: Any) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,128}", value) else "unknown"


def make_review_packet(experiment: dict) -> tuple[dict, dict]:
    """Hide variant names; bind review to the full frozen manifest and sample contents."""
    if experiment["status"] != "completed":
        raise ValueError("incomplete_experiment_not_scoreable")
    if not experiment.get("cases"):
        raise ValueError("empty_experiment_not_scoreable")
    samples = []
    for case in experiment["cases"]:
        order = ("baseline", "approved")
        if int(content_hash([experiment["experiment_id"], case["id"]])[:2], 16) % 2:
            order = tuple(reversed(order))
        for label, variant in zip(("A", "B"), order):
            run = case[variant]
            samples.append({
                "sample_id": f"{case['id']}:{label}", "question": case["question"],
                "answer": run["answer"], "answer_sha256": content_hash(run["answer"]),
                "decision": run["decision"], "qualified_evidence": run["qualified_evidence"],
                "rubric": case["rubric"],
            })
    packet = {
        "experiment_id": experiment["experiment_id"], "manifest_sha256": content_hash(experiment),
        "rubric_status": "AI-assisted; independent human review pending",
        "instructions": {
            "correctness": "关键结论是否正确；只有止答说明时可标 not_applicable",
            "premises": "是否说明题目需要的成立前提，而非只有结论",
            "citation_support": "已提供的证据是否真正支持答案，不能只看 ID/关键词",
            "appropriate_stop": "依据本轮资料是否应回答或止答",
        },
        "samples": samples,
    }
    review = {
        "experiment_id": experiment["experiment_id"], "packet_sha256": content_hash(packet),
        "reviewer": None, "method": None,
        "entries": [{"sample_id": sample["sample_id"], "answer_sha256": sample["answer_sha256"],
                     "labels": {metric: None for metric in METRICS}, "rationale": ""} for sample in samples],
    }
    return packet, review


def score_manual_review(experiment: dict, packet: dict, review: dict) -> dict:
    expected_packet, _ = make_review_packet(experiment)
    if packet != expected_packet or review.get("packet_sha256") != content_hash(packet):
        raise ValueError("review_packet_or_manifest_changed")
    if review.get("experiment_id") != experiment["experiment_id"]:
        raise ValueError("review_experiment_mismatch")
    samples = {sample["sample_id"]: sample for sample in packet["samples"]}
    entries = review.get("entries")
    if not isinstance(entries, list):
        raise ValueError("invalid_review_entries")
    by_id = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("invalid_review_entry")
        sample_id = entry.get("sample_id")
        if sample_id not in samples or sample_id in by_id:
            raise ValueError("unknown_or_duplicate_sample")
        if entry.get("answer_sha256") != samples[sample_id]["answer_sha256"]:
            raise ValueError("review_answer_changed")
        labels = entry.get("labels")
        if not isinstance(labels, dict) or set(labels) != set(METRICS) or any(
            value not in (None, "pass", "fail", "not_applicable") for value in labels.values()
        ):
            raise ValueError("invalid_review_labels")
        if "fail" in labels.values() and not str(entry.get("rationale", "")).strip():
            raise ValueError("failed_label_needs_rationale")
        by_id[sample_id] = entry
    if set(by_id) != set(samples):
        raise ValueError("review_samples_incomplete")
    annotated = sum(any(value is not None for value in entry["labels"].values()) for entry in entries)
    if annotated and (not isinstance(review.get("reviewer"), str) or not review["reviewer"].strip()
                      or review.get("method") not in ("human", "AI-assisted")):
        raise ValueError("reviewer_and_method_required")
    metrics = {}
    for metric in METRICS:
        before = after = pairs = 0
        for case in experiment["cases"]:
            order = ("baseline", "approved")
            if int(content_hash([experiment["experiment_id"], case["id"]])[:2], 16) % 2:
                order = tuple(reversed(order))
            labels = {variant: by_id[f"{case['id']}:{label}"]["labels"][metric]
                      for label, variant in zip(("A", "B"), order)}
            if all(value in ("pass", "fail") for value in labels.values()):
                pairs += 1
                before += labels["baseline"] == "pass"
                after += labels["approved"] == "pass"
        metrics[metric] = {
            "scored_pairs": pairs, "total_pairs": len(experiment["cases"]),
            "baseline_passes": before if pairs else None,
            "approved_passes": after if pairs else None,
            "pass_count_delta": after - before if pairs else None,
        }
    complete = all(all(value is not None for value in entry["labels"].values()) for entry in entries)
    return {
        "experiment_id": experiment["experiment_id"], "source": experiment["source"],
        "annotated_samples": annotated, "total_samples": len(samples),
        "review_complete": complete, "review_method": review.get("method"),
        "human_review_complete": complete and review.get("method") == "human",
        "metrics": metrics,
        "real_model_quality_measured": complete and experiment["source"] == "qwen"
        and any(metric["scored_pairs"] for metric in metrics.values()),
    }
