"""Centralized prompt management with versioning.

Usage:
    manager = PromptManager()
    prompt = manager.get("claim_extraction", version="v1")
    metadata = manager.get_metadata("claim_extraction", version="v1")
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class PromptManager:
    """Load and manage versioned prompt templates.

    Prompts are stored as text files in:
        app/prompts/templates/{prompt_name}/v{N}.txt

    Metadata is stored in:
        app/prompts/templates/{prompt_name}/metadata.json

    Examples:
        >>> manager = PromptManager()
        >>> prompt = manager.get("claim_extraction", version="v1")
        >>> latest = manager.get("claim_extraction", version="latest")
        >>> versions = manager.list_versions("claim_extraction")
        ['v1']
    """

    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize prompt manager.

        Args:
            base_dir: Directory containing prompt templates.
                      Defaults to app/prompts/templates/
        """
        if base_dir is None:
            base_dir = Path(__file__).parent / "templates"
        self.base_dir = base_dir

        if not self.base_dir.exists():
            raise FileNotFoundError(
                f"Prompt templates directory not found: {self.base_dir}"
            )

        logger.debug("PromptManager initialized with base_dir=%s", self.base_dir)

    @lru_cache(maxsize=32)
    def get(self, prompt_name: str, version: str = "latest") -> str:
        """Load a prompt template.

        Args:
            prompt_name: Name of prompt directory (e.g., "claim_extraction")
            version: Version tag (e.g., "v1", "v2") or "latest"

        Returns:
            Prompt text as a string

        Raises:
            FileNotFoundError: If prompt doesn't exist
            ValueError: If version is invalid
        """
        if version == "latest":
            version = self._get_latest_version(prompt_name)

        prompt_path = self.base_dir / prompt_name / f"{version}.txt"
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"Prompt '{prompt_name}' version '{version}' not found at {prompt_path}"
            )

        prompt_text = prompt_path.read_text(encoding="utf-8").strip()
        logger.debug(
            "Loaded prompt %s:%s (%d chars)",
            prompt_name,
            version,
            len(prompt_text),
        )
        return prompt_text

    def get_metadata(self, prompt_name: str, version: str) -> Dict:
        """Load metadata for a prompt version.

        Args:
            prompt_name: Name of prompt
            version: Version tag (e.g., "v1")

        Returns:
            Metadata dict (empty if metadata.json doesn't exist)
        """
        meta_path = self.base_dir / prompt_name / "metadata.json"
        if not meta_path.exists():
            logger.warning("No metadata.json found for prompt '%s'", prompt_name)
            return {}

        try:
            metadata = json.loads(meta_path.read_text())
            return metadata.get(version, {})
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in %s: %s", meta_path, exc)
            return {}

    def list_versions(self, prompt_name: str) -> List[str]:
        """List all available versions for a prompt.

        Args:
            prompt_name: Name of prompt

        Returns:
            List of version tags (e.g., ["v1", "v2"])
        """
        prompt_dir = self.base_dir / prompt_name
        if not prompt_dir.exists():
            return []

        versions = [p.stem for p in prompt_dir.glob("v*.txt")]
        versions.sort(key=self._version_sort_key)
        return versions

    def _get_latest_version(self, prompt_name: str) -> str:
        """Determine the latest version by sorting version tags.

        Args:
            prompt_name: Name of prompt

        Returns:
            Latest version tag (e.g., "v2")

        Raises:
            FileNotFoundError: If no versions exist
        """
        versions = self.list_versions(prompt_name)
        if not versions:
            raise FileNotFoundError(
                f"No versions found for prompt '{prompt_name}' "
                f"in {self.base_dir / prompt_name}"
            )
        return versions[-1]  # Last after sorting

    @staticmethod
    def _version_sort_key(version: str) -> int:
        """Extract numeric part from version tag for sorting.

        Examples:
            "v1" -> 1
            "v10" -> 10
            "v2a" -> 2
        """
        numeric = "".join(filter(str.isdigit, version))
        return int(numeric) if numeric else 0
