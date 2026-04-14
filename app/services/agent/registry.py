"""Skill registry — central place to register and look up skills."""

from __future__ import annotations

from app.services.agent.skill import Skill


class SkillRegistry:
    """Singleton registry that maps skill names to implementations."""

    _instance: SkillRegistry | None = None
    _skills: dict[str, Skill]

    def __new__(cls) -> SkillRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._skills = {}
        return cls._instance

    def register(self, skill: Skill) -> None:
        """Register a skill instance."""
        if not skill.name:
            raise ValueError(f"Skill {skill.__class__.__name__} has no name")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        """List all registered skills."""
        return list(self._skills.values())

    def get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-compatible tool schemas for all skills (used by router)."""
        return [skill.get_schema() for skill in self._skills.values()]

    def unregister(self, name: str) -> None:
        """Remove a skill from registry."""
        self._skills.pop(name, None)

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None


# Global registry instance
registry = SkillRegistry()


def register_skill(skill: Skill) -> Skill:
    """Convenience function to register a skill."""
    registry.register(skill)
    return skill
