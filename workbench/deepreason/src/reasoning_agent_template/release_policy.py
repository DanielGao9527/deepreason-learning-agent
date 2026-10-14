"""Final publication boundary after the worker has drafted an answer."""
from __future__ import annotations

from dataclasses import dataclass

from reasoning_agent_template.models import GateDecision


@dataclass(frozen=True)
class ReleaseDecision:
    answer: str
    status: str
    gate_status: str
    reason: str
    draft_withheld: bool


def decide_release(draft: str, gates: list[GateDecision]) -> ReleaseDecision:
    """Do not expose a worker draft when the final workflow gate did not allow it.

    An allowed gate means only that the existing gate rules passed. It does not
    establish that each claim in the draft is supported by evidence.
    """
    gate_status = gates[-1].status if gates else "missing"
    if gate_status == "allow":
        return ReleaseDecision(
            answer=draft,
            status="released_gate_only",
            gate_status=gate_status,
            reason="existing_gate_allowed; claims_not_independently_checked",
            draft_withheld=False,
        )
    if gate_status == "deny":
        answer = "本轮高风险请求未通过保护性证据门禁，不能提供执行建议。"
    else:
        answer = "本轮证据或执行门禁未通过，暂不能提供确定结论；请补充可核对的依据后重试。"
    return ReleaseDecision(
        answer=answer,
        status="withheld",
        gate_status=gate_status,
        reason=f"gate_{gate_status}",
        draft_withheld=True,
    )
