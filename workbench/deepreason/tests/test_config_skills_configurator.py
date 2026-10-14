import tempfile
import unittest
from pathlib import Path

from reasoning_agent_template.config import load_agent_config
from reasoning_agent_template.configurator import ConfigAssistant
from reasoning_agent_template.skills import SkillRegistry


EXPECTED_SKILLS = {
    "project-intake",
    "evidence-first",
    "state-gates",
    "knowledge-rag",
    "memory-consolidation",
    "minimal-change",
    "self-evolution",
    "configurator",
    "testing-verification",
}


class ConfigSkillsConfiguratorTests(unittest.TestCase):
    def test_sample_agent_yaml_loads_required_sections(self):
        config = load_agent_config(Path("agent.yaml"))

        self.assertEqual(config.identity["name"], "reasoning-agent-template")
        self.assertIn("planner", config.models)
        self.assertEqual(config.knowledge["directory"], "knowledge")
        self.assertIn("write_file", config.gates["approval_required_actions"])
        self.assertIn("evidence-first", config.skills["enabled"])

    def test_skill_registry_loads_expected_constraint_packs(self):
        registry = SkillRegistry(Path("skills"))
        skills = registry.load()

        self.assertTrue(EXPECTED_SKILLS.issubset(set(skills)))
        for name in EXPECTED_SKILLS:
            self.assertEqual(skills[name].name, name)
            self.assertGreater(len(skills[name].description), 20)
            self.assertTrue(skills[name].path.name == "SKILL.md")

    def test_config_assistant_creates_project_config_and_acceptance_tests(self):
        assistant = ConfigAssistant.from_schema(Path("configs/agent.schema.json"))

        draft = assistant.create_project_config(
            name="research-agent",
            purpose="Answer research questions with cited evidence.",
            audience="technical users",
            knowledge_dir="knowledge",
        )
        recommended = assistant.recommend_skills(
            ["knowledge base", "evidence", "long-term memory", "self evolution"]
        )
        acceptance_tests = assistant.generate_acceptance_tests(draft)

        self.assertEqual(draft["identity"]["name"], "research-agent")
        self.assertEqual(draft["knowledge"]["directory"], "knowledge")
        self.assertIn("knowledge-rag", recommended)
        self.assertIn("evidence-first", recommended)
        self.assertTrue(any("evidence" in item.lower() for item in acceptance_tests))
        self.assertTrue(any("memory" in item.lower() for item in acceptance_tests))

    def test_config_assistant_writes_yaml_without_external_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            assistant = ConfigAssistant.from_schema(Path("configs/agent.schema.json"))
            target = Path(tmp) / "agent.yaml"
            draft = assistant.create_project_config(
                name="local-agent",
                purpose="Keep project-local reasoning state.",
                audience="developers",
                knowledge_dir="knowledge",
            )

            assistant.write_yaml(draft, target)

            self.assertIn("local-agent", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
