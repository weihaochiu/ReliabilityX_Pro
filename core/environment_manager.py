"""core/environment_manager.py

Stage 2.5.4 bugfix update:
- Add instance update persistence so Environment tabs can save relay assignment
  and default recipe changes through a stable core-layer API.
- Keep all JSON I/O inside the model layer without importing Qt classes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class EnvironmentInstance:
    """Environment instance metadata.

    Attributes:
        instance_id: Stable instance identifier.
        env_type: Environment type such as ``climate`` / ``glovebox`` /
            ``indoor``.
        title: Human-readable title.
        smu_plus_start: SMU plus relay start index.
        smu_plus_end: SMU plus relay end index.
        smu_minus_start: SMU minus relay start index.
        smu_minus_end: SMU minus relay end index.
        default_env_recipe: Default environment recipe id.
    """

    instance_id: str
    env_type: str
    title: str
    smu_plus_start: int
    smu_plus_end: int
    smu_minus_start: int
    smu_minus_end: int
    default_env_recipe: str = ""


class EnvironmentManager:
    """JSON-backed environment configuration manager."""

    def __init__(
        self,
        environment_profiles_path: str | Path = "config/environment_profiles.json",
        environment_control_recipes_path: str | Path = "config/environment_control_recipes.json",
    ) -> None:
        self.environment_profiles_path = Path(environment_profiles_path)
        self.environment_control_recipes_path = Path(environment_control_recipes_path)
        self._profiles: dict[str, Any] = {}
        self._recipes: dict[str, Any] = {}
        self.reload_all()

    def _load_json(self, path: Path) -> dict[str, Any]:
        """Load one JSON file safely.

        Args:
            path: JSON path.

        Returns:
            dict[str, Any]: Parsed JSON object or empty dict when unavailable.
        """
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
        except Exception:
            return {}
        return {}

    def _save_json(self, path: Path, payload: dict[str, Any]) -> None:
        """Save one JSON file safely.

        Args:
            path: Destination JSON path.
            payload: JSON payload to write.

        Raises:
            IOError: If the file cannot be written.
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            raise IOError(f"Failed to write JSON file: {path}") from exc

    def reload_all(self) -> None:
        """Reload environment-related JSON files."""
        self._profiles = self._load_json(self.environment_profiles_path)
        self._recipes = self._load_json(self.environment_control_recipes_path)

    def list_instances(self, environment_type: str | None = None) -> list[str]:
        """List environment instance ids.

        Args:
            environment_type: Optional filter.

        Returns:
            list[str]: Instance ids.
        """
        instances = self._profiles.get("instances", {})
        if not isinstance(instances, dict):
            return []
        if environment_type is None:
            return list(instances.keys())
        return [
            key for key, value in instances.items()
            if isinstance(value, dict) and value.get("type") == environment_type
        ]

    def get_instance(self, instance_id: str) -> EnvironmentInstance | None:
        """Return a typed environment instance.

        Args:
            instance_id: Instance id.

        Returns:
            EnvironmentInstance | None: Typed object when found.
        """
        payload = (self._profiles.get("instances") or {}).get(instance_id)
        if not isinstance(payload, dict):
            return None
        return EnvironmentInstance(
            instance_id=instance_id,
            env_type=str(payload.get("type", "")),
            title=str(payload.get("title", instance_id)),
            smu_plus_start=int(payload.get("smu_plus_start", 0)),
            smu_plus_end=int(payload.get("smu_plus_end", 0)),
            smu_minus_start=int(payload.get("smu_minus_start", 32)),
            smu_minus_end=int(payload.get("smu_minus_end", 32)),
            default_env_recipe=str(payload.get("default_env_recipe", "")),
        )

    def update_instance(self, instance_id: str, payload: dict[str, Any]) -> None:
        """Upsert one environment instance back into profiles JSON.

        Args:
            instance_id: Instance id to update.
            payload: Updated instance payload. Supported keys include
                ``type``, ``title``, relay ranges, and ``default_env_recipe``.

        Raises:
            ValueError: If ``instance_id`` is empty.
            IOError: If persistence fails.
        """
        if not str(instance_id).strip():
            raise ValueError("instance_id must not be empty.")

        instances = self._profiles.setdefault("instances", {})
        if not isinstance(instances, dict):
            instances = {}
            self._profiles["instances"] = instances

        existing = instances.get(instance_id, {})
        if not isinstance(existing, dict):
            existing = {}

        merged = {
            "type": str(payload.get("type", existing.get("type", ""))),
            "title": str(payload.get("title", existing.get("title", instance_id))),
            "smu_plus_start": int(payload.get("smu_plus_start", existing.get("smu_plus_start", 0))),
            "smu_plus_end": int(payload.get("smu_plus_end", existing.get("smu_plus_end", 0))),
            "smu_minus_start": int(payload.get("smu_minus_start", existing.get("smu_minus_start", 32))),
            "smu_minus_end": int(payload.get("smu_minus_end", existing.get("smu_minus_end", 32))),
            "default_env_recipe": str(
                payload.get("default_env_recipe", existing.get("default_env_recipe", ""))
            ),
        }
        instances[instance_id] = merged
        self._save_json(self.environment_profiles_path, self._profiles)
        self.reload_all()

    def get_relay_range(self, instance_id: str) -> dict[str, tuple[int, int]]:
        """Return SMU+ / SMU- relay ranges for one instance.

        Args:
            instance_id: Instance id.

        Returns:
            dict[str, tuple[int, int]]: Relay start/end pairs.
        """
        item = self.get_instance(instance_id)
        if item is None:
            return {"smu_plus": (0, 0), "smu_minus": (32, 32)}
        return {
            "smu_plus": (item.smu_plus_start, item.smu_plus_end),
            "smu_minus": (item.smu_minus_start, item.smu_minus_end),
        }

    def list_environment_recipes(self, environment_type: str | None = None) -> list[dict[str, Any]]:
        """List environment recipes, optionally filtered by environment type.

        Args:
            environment_type: Optional filter.

        Returns:
            list[dict[str, Any]]: Recipe dictionaries.
        """
        recipes = self._recipes.get("recipes", [])
        if not isinstance(recipes, list):
            return []
        cleaned = [item for item in recipes if isinstance(item, dict)]
        if environment_type is None:
            return cleaned
        return [
            item for item in cleaned
            if environment_type in item.get("environment_types", [])
            or item.get("environment_type") == environment_type
        ]

    def get_environment_recipe_ids(self, environment_type: str | None = None) -> list[str]:
        """Return environment recipe ids.

        Args:
            environment_type: Optional filter.

        Returns:
            list[str]: Recipe ids.
        """
        return [
            str(item.get("id", ""))
            for item in self.list_environment_recipes(environment_type)
            if str(item.get("id", ""))
        ]

    def get_recipe_description(self, recipe_id: str) -> str:
        """Return description for one recipe id.

        Args:
            recipe_id: Recipe id.

        Returns:
            str: Recipe description, or empty string when missing.
        """
        for item in self.list_environment_recipes():
            if str(item.get("id", "")) == str(recipe_id):
                return str(item.get("description", ""))
        return ""
