"""A model search rewrite cannot replace the goal used for plans and gates."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from reasoning_agent_template.knowledge import LocalKnowledgeBase
from reasoning_agent_template.learning import (
    LearningAssistant, LearningRouteReviewError, LearningTemplateCoordinator, learning_config,
)
from reasoning_agent_template.llm import ChatResult
from reasoning_agent_template.models import AgentState
from reasoning_agent_template.workflow import TemplateCoordinator
from tests.test_learning_mvp import CORPUS, ReviewedLearningClient


class RewrittenRouteClient(ReviewedLearningClient):
    def __init__(self, query):
        super().__init__()
        self.query = query

    def chat(self, messages, **kwargs):
        if "ROUTING_DECISION_JSON" in messages[-1].content:
            self.calls.append("route")
            return ChatResult(content=json.dumps({
                "difficulty": "simple", "workflow": "routine", "evidence_mode": "optional",
                "evidence_strictness": "none", "risk_level": "low", "category": "routine",
                "sources": ["rag"], "confidence": 0.8, "retrieval_query": self.query,
            }, ensure_ascii=False), model=self.model, raw={"offline": True})
        return super().chat(messages, **kwargs)


class LearningGoalBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(CORPUS, self.root / "knowledge")

    def tearDown(self):
        self.temp.cleanup()

    def test_destructive_goal_is_denied_even_if_search_rewrite_is_descriptive_or_unrelated(self):
        for index, query in enumerate(("删除生产环境数据的流程与风险", "哈希表", "二叉树是什么？")):
            with self.subTest(query=query):
                client = RewrittenRouteClient(query)
                assistant = LearningAssistant(self.root, client=client)
                result = assistant.ask("请删除生产环境数据。", thread_id=f"protected-{index}")
                self.assertEqual(result["gates"]["decisions"][-1]["status"], "deny")
                self.assertEqual(result["learning"]["decision"], "blocked")
                self.assertEqual(client.calls, ["route", "reviewer"])
                self.assertEqual(result["evidence"]["status"], "protected_denied")
                saved = assistant.orchestrator.session_store.load(f"protected-{index}")
                self.assertEqual(saved.messages[-1]["content"], result["answer"])

    def test_original_comparison_still_executes_two_subject_queries_after_router_rewrite(self):
        client = RewrittenRouteClient("什么是哈希冲突？")
        queries = []
        retrieve = LocalKnowledgeBase.retrieve

        def observe(kb, query, **kwargs):
            queries.append(query)
            return retrieve(kb, query, **kwargs)

        with patch.object(LocalKnowledgeBase, "retrieve", observe):
            result = LearningAssistant(self.root, client=client).ask(
                "哈希表和二叉搜索树有什么区别？", thread_id="comparison",
            )
        self.assertEqual(queries, ["哈希表", "二叉搜索树"])
        self.assertEqual(result["workflow"]["execution_plan"]["status"], "completed")
        self.assertEqual(result["learning"]["decision"], "answered")

    def test_readonly_rewrite_is_used_for_retrieval_and_recorded_without_replacing_question(self):
        query = "哈希函数 槽位 冲突"
        client = RewrittenRouteClient(query)
        queries = []
        retrieve = LocalKnowledgeBase.retrieve

        def observe(kb, actual_query, **kwargs):
            queries.append(actual_query)
            return retrieve(kb, actual_query, **kwargs)

        with patch.object(LocalKnowledgeBase, "retrieve", observe):
            result = LearningAssistant(self.root, client=client).ask("什么是哈希冲突？", thread_id="readonly")
        self.assertEqual(queries, [query])
        self.assertEqual(result["question"], "什么是哈希冲突？")
        self.assertEqual(next(event["retrieval_query"] for event in result["events"]
                              if event.get("kind") == "learning_retrieval_query"), query)

    def test_retrieval_failure_restores_original_goal(self):
        coordinator = LearningTemplateCoordinator(config=learning_config(self.root), workspace_root=self.root)
        state = AgentState(user_goal="请删除生产环境数据。")
        state.routing_decision = {"retrieval_query": "哈希表"}
        with patch.object(TemplateCoordinator, "_retrieve", side_effect=TimeoutError("test fault")), \
             self.assertRaises(TimeoutError):
            coordinator._retrieve(state)
        self.assertEqual(state.user_goal, "请删除生产环境数据。")

    def test_route_examples_are_valid_objects_and_real_union_receipt_is_still_rejected(self):
        orchestrator = LearningAssistant(self.root, client=ReviewedLearningClient()).orchestrator
        route = orchestrator._routing_messages("什么是哈希冲突？", short_term_memory=[], long_term_memory=[])
        reviewer = orchestrator._reviewer_messages("什么是哈希冲突？", {},
                                                   short_term_memory=[], long_term_memory=[])
        for messages in (route, reviewer):
            example = json.JSONDecoder().raw_decode(messages[-1].content.split("schema:\n", 1)[1])[0]
            self.assertEqual(example["category"], "technical_claim")
            self.assertEqual(example["evidence_mode"], "required")
            self.assertIn("用户输入:\n什么是哈希冲突？", messages[-1].content)
        self.assertEqual(orchestrator._parse_route_review(json.dumps(example))["review_status"], "approve")
        example["category"] = "technical_claim|hard_reasoning"
        with self.assertRaisesRegex(LearningRouteReviewError, "invalid_review_route_field"):
            orchestrator._parse_route_review(json.dumps(example))

    def test_reviewer_receives_route_projection_without_runtime_metadata(self):
        orchestrator = LearningAssistant(self.root, client=ReviewedLearningClient()).orchestrator
        route = {"difficulty": "hard", "category": "technical_claim", "risk_level": "high",
                 "source": "llm", "learning_policy": "local_corpus_required",
                 "learning_risk_floor": {"category": "high_risk_action"}}
        messages = orchestrator._reviewer_messages("请删除生产环境数据。", route,
                                                   short_term_memory=[], long_term_memory=[])
        actual = json.JSONDecoder().raw_decode(messages[-1].content.split("Coordinator 路由 JSON:\n", 1)[1])[0]
        self.assertEqual(actual, {"difficulty": "hard", "category": "technical_claim", "risk_level": "high"})
        self.assertIn("learning_risk_floor", route)


if __name__ == "__main__":
    unittest.main()
