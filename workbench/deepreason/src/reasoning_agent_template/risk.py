from __future__ import annotations

from reasoning_agent_template.models import EvidenceRequirement


ACADEMIC_TERMS = [
    "论文",
    "研究",
    "学术",
    "综述",
    "文献",
    "引用",
    "关键论文",
    "最新研究",
    "研究进展",
    "实验",
    "数据集",
    "meta分析",
    "系统综述",
    "citation",
    "citations",
    "paper",
    "papers",
    "literature",
    "review",
    "systematic review",
    "arxiv",
    "doi",
    "dataset",
    "benchmark",
]

REGULATED_TERMS = [
    "医疗",
    "医学",
    "诊断",
    "临床",
    "治疗",
    "用药",
    "法律",
    "合同",
    "诉讼",
    "投资",
    "金融",
    "保险",
    "medical",
    "clinical",
    "diagnosis",
    "treatment",
    "legal",
    "investment",
    "finance",
]

DIRECT_ADVICE_TERMS = [
    "我该",
    "帮我诊断",
    "治疗方案",
    "用什么药",
    "买入",
    "卖出",
    "法律意见",
    "medical advice",
    "diagnose me",
    "treatment plan",
    "legal advice",
    "buy or sell",
]

HIGH_RISK_ACTION_TERMS = [
    "高风险",
    "高危",
    "生产环境",
    "删库",
    "删除数据",
    "执行命令",
    "写文件",
    "修改文件",
    "外部调用",
    "自进化",
    "更新技能",
    "长期记忆",
    "安全漏洞",
    "权限",
    "密钥",
    "high-risk",
    "critical",
    "production",
    "delete",
    "execute command",
    "write file",
    "security vulnerability",
    "credential",
    "api key",
]

HARD_REASONING_TERMS = [
    "强推理",
    "重推理",
    "高难",
    "复杂决策",
    "证明",
    "审计",
    "根因分析",
    "架构决策",
    "迁移方案",
    "hard reasoning",
    "deep reasoning",
    "root cause",
    "architecture decision",
    "audit",
    "migration plan",
]

DECISION_ANALYSIS_TERMS = [
    "比较",
    "对比",
    "评估",
    "选择建议",
    "优缺点",
    "利弊",
    "取舍",
    "权衡",
    "方案",
    "策略",
    "路线图",
    "可行性",
    "企业知识库",
    "技术选型",
    "架构选型",
    "可靠建议",
    "可靠判断",
    "compare",
    "comparison",
    "evaluate",
    "tradeoff",
    "trade-off",
    "recommendation",
    "selection",
    "strategy",
    "roadmap",
]

FACTUAL_EVIDENCE_TERMS = [
    "最新",
    "当前",
    "现在",
    "主流",
    "趋势",
    "变化",
    "可靠",
    "依据",
    "来源",
    "数据",
    "事实",
    "排名",
    "市场",
    "recent",
    "latest",
    "current",
    "trend",
    "evidence",
    "source",
    "sources",
    "data",
    "market",
]

EXPLICIT_EVIDENCE_REQUEST_TERMS = [
    "给出依据",
    "提供依据",
    "相应依据",
    "相应的依据",
    "对应依据",
    "对应的依据",
    "相关依据",
    "相关的依据",
    "依据是什么",
    "有什么依据",
    "支撑依据",
    "证据支撑",
    "给出证据",
    "提供证据",
    "引用来源",
    "给出来源",
    "提供来源",
    "来源是什么",
    "参考资料",
    "凭什么",
    "根据什么",
    "可验证来源",
    "cite your sources",
    "provide sources",
    "with sources",
    "sources for",
    "provide evidence",
    "supporting evidence",
    "what evidence",
    "basis for",
    "references for",
    "cite evidence",
]

TECHNICAL_JUDGMENT_TERMS = [
    "为什么",
    "为何",
    "怎么",
    "如何",
    "是什么",
    "适合",
    "不适合",
    "最佳实践",
    "实践",
    "原理",
    "机制",
    "区别",
    "差异",
    "有什么区别",
    "优缺点",
    "优劣",
    "推荐",
    "建议",
    "应该",
    "是否",
    "能否",
    "可行",
    "选型",
    "选",
    "why",
    "how",
    "what is",
    "best practice",
    "best practices",
    "difference",
    "differences",
    "vs",
    "versus",
    "suitable",
    "recommend",
    "recommendation",
    "should",
    "compare",
]

TECHNICAL_DOMAIN_TERMS = [
    "数据库",
    "向量数据库",
    "框架",
    "模型",
    "平台",
    "工具",
    "系统",
    "架构",
    "agent",
    "rag",
    "知识库",
    "database",
    "framework",
    "model",
    "platform",
    "architecture",
    "system",
    "langgraph",
    "deep agents",
    "deepagents",
    "llm",
    "embedding",
    "vector",
    "chroma",
    "milvus",
    "qdrant",
    "weaviate",
    "pinecone",
    "faiss",
    "postgres",
    "neo4j",
    "state machine",
    "workflow",
    "api",
]


def classify_evidence_requirement(value: str) -> EvidenceRequirement:
    text = value.lower().strip()
    if _is_local_template_introspection(text):
        return EvidenceRequirement(
            mode="optional",
            risk_level="none",
            category="routine",
            reasons=["local template introspection"],
            sources=[],
        )
    matched_academic = _matches(text, ACADEMIC_TERMS)
    matched_regulated = _matches(text, REGULATED_TERMS)
    matched_direct_advice = _matches(text, DIRECT_ADVICE_TERMS)
    matched_high_risk = _matches(text, HIGH_RISK_ACTION_TERMS)
    matched_hard_reasoning = _matches(text, HARD_REASONING_TERMS)
    matched_decision = _matches(text, DECISION_ANALYSIS_TERMS)
    matched_factual = _matches(text, FACTUAL_EVIDENCE_TERMS)
    matched_explicit_evidence = _matches(text, EXPLICIT_EVIDENCE_REQUEST_TERMS)
    matched_technical_judgment = _matches(text, TECHNICAL_JUDGMENT_TERMS)
    matched_technical = _matches(text, TECHNICAL_DOMAIN_TERMS)

    if matched_direct_advice:
        return EvidenceRequirement(
            mode="required",
            risk_level="high",
            category="regulated_advice",
            reasons=_reasons("direct regulated advice", matched_direct_advice + matched_regulated),
            sources=["rag", "papers", "web", "user_experience"],
        )

    if matched_academic:
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="academic",
            reasons=_reasons("academic/research claim", matched_academic + matched_regulated),
            sources=["rag", "papers", "web", "user_experience"],
        )

    if matched_explicit_evidence:
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="explicit_evidence_request",
            reasons=_reasons("user explicitly requested evidence", matched_explicit_evidence),
            sources=["rag", "web", "papers", "user_experience"],
        )

    if matched_high_risk:
        return EvidenceRequirement(
            mode="required",
            risk_level="high",
            category="high_risk_action",
            reasons=_reasons("high-risk action or protected asset", matched_high_risk),
            sources=["rag", "user_experience"],
        )

    if matched_regulated:
        return EvidenceRequirement(
            mode="required",
            risk_level="high",
            category="regulated_domain",
            reasons=_reasons("regulated domain", matched_regulated),
            sources=["rag", "papers", "web", "user_experience"],
        )

    if matched_hard_reasoning:
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="hard_reasoning",
            reasons=_reasons("hard reasoning", matched_hard_reasoning),
            sources=["rag", "web", "papers", "user_experience"],
        )

    if matched_decision and (matched_factual or matched_technical):
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="decision_analysis",
            reasons=_reasons("complex decision analysis", matched_decision + matched_factual + matched_technical),
            sources=["rag", "web", "papers", "user_experience"],
        )

    if matched_factual and matched_technical:
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="current_factual",
            reasons=_reasons("current factual or technical claim", matched_factual + matched_technical),
            sources=["rag", "web", "papers", "user_experience"],
        )

    if matched_technical_judgment and (matched_technical or _has_technical_name(value)):
        return EvidenceRequirement(
            mode="required",
            risk_level="medium",
            category="technical_claim",
            reasons=_reasons(
                "technical judgment likely needs evidence",
                matched_technical_judgment + matched_technical,
            ),
            sources=["rag", "web", "papers", "user_experience"],
        )

    return EvidenceRequirement(
        mode="optional",
        risk_level="none",
        category="routine",
        reasons=["routine chat or low-risk explanation"],
        sources=[],
    )


def is_explicit_evidence_request(value: str) -> bool:
    return bool(_matches(value.lower().strip(), EXPLICIT_EVIDENCE_REQUEST_TERMS))


def _matches(text: str, terms: list[str]) -> list[str]:
    return [term for term in terms if term.lower() in text]


def _has_technical_name(text: str) -> bool:
    for token in text.replace("-", " ").split():
        cleaned = "".join(char for char in token if char.isalnum())
        if len(cleaned) >= 3 and any(char.isalpha() for char in cleaned) and any(char.isupper() for char in token):
            return True
    return False


def _is_local_template_introspection(text: str) -> bool:
    local_markers = [
        "这个模板",
        "当前模板",
        "这个 agent",
        "当前 agent",
        "这个agent",
        "当前agent",
        "你这个",
        "本模板",
        "本系统",
        "this template",
        "this agent",
        "current agent",
    ]
    introspection_markers = [
        "工作流",
        "证据系统",
        "状态机",
        "门禁",
        "记忆",
        "技能",
        "调试",
        "workflow",
        "evidence system",
        "state machine",
        "gate",
        "memory",
        "skills",
        "debug",
    ]
    return any(marker in text for marker in local_markers) and any(
        marker in text for marker in introspection_markers
    )


def _reasons(label: str, terms: list[str]) -> list[str]:
    unique_terms = list(dict.fromkeys(terms))
    if not unique_terms:
        return [label]
    return [f"{label}: {', '.join(unique_terms[:8])}"]
