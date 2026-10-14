import json
import tempfile
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote_plus

from reasoning_agent_template.evidence import EvidenceLedger
from reasoning_agent_template.external_evidence import ExternalEvidenceSearch


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def read(self):
        return json.dumps(self.body).encode("utf-8")


class _FakeTextResponse(_FakeResponse):
    def read(self):
        return str(self.body).encode("utf-8")


class ExternalEvidenceTests(unittest.TestCase):
    def test_semantic_scholar_results_are_normalized_into_citable_evidence(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "data": [
                        {
                            "paperId": "abc123",
                            "title": "Large Language Models in Clinical Diagnosis",
                            "abstract": "A review of LLMs for diagnostic decision support.",
                            "year": 2025,
                            "url": "https://www.semanticscholar.org/paper/abc123",
                            "authors": [{"name": "Ada Chen"}],
                            "citationCount": 42,
                        }
                    ]
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            results = searcher.retrieve(
                "请综述大语言模型在医学诊断中的最新研究进展，并给出关键论文依据。",
                top_k=2,
                sources=["papers"],
            )
            items = ledger.list()

        self.assertEqual(len(results), 1)
        self.assertIn("large language models", unquote_plus(captured["url"]).lower())
        self.assertTrue(results[0].evidence_id.startswith("ev_"))
        self.assertIn("Large Language Models in Clinical Diagnosis", results[0].text)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_type, "paper")
        self.assertEqual(items[0].uri, "https://www.semanticscholar.org/paper/abc123")
        self.assertIn("external:semantic_scholar", items[0].used_for)

    def test_user_experience_can_be_recorded_as_evidence_when_prompt_contains_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=lambda request, timeout: None)

            results = searcher.retrieve(
                "根据我的经验：上次生产迁移失败是因为索引缺失。请做根因分析。",
                top_k=3,
                sources=["user_experience"],
            )
            items = ledger.list()

        self.assertEqual(len(results), 1)
        self.assertEqual(items[0].source_type, "user_experience")
        self.assertIn("生产迁移失败", items[0].summary)

    def test_web_results_are_normalized_into_citable_evidence(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            return _FakeResponse(
                {
                    "Heading": "LangGraph",
                    "AbstractText": "LangGraph is a framework for building stateful agents.",
                    "AbstractURL": "https://example.com/langgraph",
                    "RelatedTopics": [
                        {
                            "Text": "LangGraph persistence supports long-running workflows.",
                            "FirstURL": "https://example.com/langgraph-persistence",
                        }
                    ],
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            results = searcher.retrieve(
                "请给出 LangGraph 适合做多 Agent 状态机的依据",
                top_k=3,
                sources=["web"],
            )
            items = ledger.list()

        self.assertIn("api.duckduckgo.com", captured["url"])
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(items[0].source_type, "web")
        self.assertIn("external:web", items[0].used_for)
        self.assertIn("stateful agents", results[0].text)

    def test_web_search_falls_back_to_html_results_when_instant_answer_is_empty(self):
        captured_urls = []

        def fake_urlopen(request, timeout):
            captured_urls.append(request.full_url)
            if "api.duckduckgo.com" in request.full_url:
                return _FakeResponse({"RelatedTopics": []})
            html = """
            <html><body>
              <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fvector-db">Vector database guide</a>
              <a class="result__snippet">A practical comparison for vector database selection.</a>
            </body></html>
            """
            return _FakeTextResponse(html)

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            results = searcher.retrieve(
                "企业知识库 向量数据库 选型 依据",
                top_k=3,
                sources=["web"],
            )
            items = ledger.list()

        self.assertTrue(any("duckduckgo.com/html" in url for url in captured_urls))
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(items[0].source_type, "web")
        self.assertEqual(items[0].uri, "https://example.com/vector-db")
        self.assertIn("Vector database guide", results[0].text)

    def test_chinese_web_query_is_expanded_for_external_search(self):
        captured_urls = []

        def fake_urlopen(request, timeout):
            captured_urls.append(request.full_url)
            return _FakeResponse({"RelatedTopics": []})

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            searcher.retrieve(
                "请给出企业知识库向量数据库选型相应的依据",
                top_k=3,
                sources=["web"],
            )

        joined = " ".join(unquote_plus(url).lower() for url in captured_urls)
        self.assertIn("enterprise knowledge base", joined)
        self.assertIn("vector database", joined)
        self.assertIn("selection", joined)

    def test_materials_science_query_is_expanded_for_paper_search(self):
        captured_urls = []

        def fake_urlopen(request, timeout):
            captured_urls.append(request.full_url)
            if "semanticscholar" in request.full_url:
                return _FakeResponse({"data": []})
            if "crossref" in request.full_url:
                return _FakeResponse({"message": {"items": []}})
            return _FakeResponse({"RelatedTopics": []})

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            searcher.retrieve(
                "高熵合金的强度影响因素",
                top_k=3,
                sources=["papers"],
            )

        joined = " ".join(unquote_plus(url).lower() for url in captured_urls)
        self.assertIn("high entropy alloys", joined)
        self.assertIn("strength", joined)
        self.assertIn("factors", joined)

    def test_irrelevant_paper_results_are_filtered_out(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request.full_url)
            if "semanticscholar" in request.full_url:
                return _FakeResponse({"data": []})
            return _FakeResponse(
                {
                    "message": {
                        "items": [
                            {
                                "DOI": "10.0000/unrelated",
                                "title": ["Knowledge-Based Database Assistant"],
                                "container-title": ["Knowledge-Base Assisted Database Retrieval Systems"],
                                "is-referenced-by-count": 2,
                            }
                        ]
                    }
                }
            )

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            results = searcher.retrieve(
                "请给出企业知识库向量数据库选型相应的依据",
                top_k=3,
                sources=["papers"],
            )

        self.assertEqual(results, [])
        self.assertEqual(ledger.list(), [])

    def test_external_search_records_provider_errors_and_empty_results(self):
        def fake_urlopen(request, timeout):
            if "semanticscholar" in request.full_url:
                raise HTTPError(request.full_url, 429, "Too Many Requests", hdrs=None, fp=None)
            if "crossref" in request.full_url:
                return _FakeResponse({"message": {"items": []}})
            return _FakeResponse({"RelatedTopics": []})

        with tempfile.TemporaryDirectory() as tmp:
            ledger = EvidenceLedger(Path(tmp) / "evidence.jsonl")
            searcher = ExternalEvidenceSearch(ledger=ledger, urlopen=fake_urlopen)

            results = searcher.retrieve(
                "请综述大语言模型在医学诊断中的最新研究进展，并给出关键论文依据。",
                top_k=3,
                sources=["papers", "web"],
            )

        self.assertEqual(results, [])
        joined = " ".join(item["message"] for item in searcher.diagnostics)
        self.assertIn("429", joined)
        self.assertTrue(any(item["status"] == "empty" for item in searcher.diagnostics))


if __name__ == "__main__":
    unittest.main()
