from __future__ import annotations

from pathlib import Path

from reasoning_agent_template.models import SkillMetadata


class SkillRegistry:
    """Load Deep Agents-style skill metadata from local SKILL.md files."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def load(self) -> dict[str, SkillMetadata]:
        skills: dict[str, SkillMetadata] = {}
        if not self.root.exists():
            return skills
        for skill_file in sorted(self.root.glob("*/SKILL.md")):
            metadata = _frontmatter(skill_file)
            name = metadata.get("name", skill_file.parent.name)
            description = metadata.get("description", "")
            skills[name] = SkillMetadata(name=name, description=description, path=skill_file)
        return skills


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    _, _, rest = text.partition("---")
    header, _, _ = rest.partition("---")
    data: dict[str, str] = {}
    for line in header.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip('"').strip("'")
    return data
