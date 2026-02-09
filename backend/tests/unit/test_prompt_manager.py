"""Unit tests for PromptManager."""

import json
import pytest
from pathlib import Path

from app.prompts.manager import PromptManager


@pytest.fixture
def temp_prompts_dir(tmp_path):
    """Create a temporary prompts directory for testing."""
    prompts_dir = tmp_path / "prompts"
    claim_dir = prompts_dir / "claim_extraction"
    claim_dir.mkdir(parents=True)

    # Create v1 prompt
    (claim_dir / "v1.txt").write_text("Prompt version 1 content")

    # Create v2 prompt
    (claim_dir / "v2.txt").write_text("Prompt version 2 content")

    # Create metadata
    metadata = {
        "v1": {"created": "2026-01-01", "description": "First version"},
        "v2": {"created": "2026-02-01", "description": "Second version"},
    }
    (claim_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return prompts_dir


def test_get_prompt_by_version(temp_prompts_dir):
    """Load a specific prompt version."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    prompt = manager.get("claim_extraction", version="v1")
    assert prompt == "Prompt version 1 content"


def test_get_latest_prompt(temp_prompts_dir):
    """Load latest prompt version."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    prompt = manager.get("claim_extraction", version="latest")
    assert prompt == "Prompt version 2 content"


def test_get_metadata(temp_prompts_dir):
    """Load metadata for a prompt version."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    metadata = manager.get_metadata("claim_extraction", version="v1")
    assert metadata["description"] == "First version"


def test_list_versions(temp_prompts_dir):
    """List all versions of a prompt."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    versions = manager.list_versions("claim_extraction")
    assert versions == ["v1", "v2"]


def test_prompt_not_found(temp_prompts_dir):
    """Raise error if prompt doesn't exist."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    with pytest.raises(FileNotFoundError, match="not found"):
        manager.get("nonexistent", version="v1")


def test_version_not_found(temp_prompts_dir):
    """Raise error if version doesn't exist."""
    manager = PromptManager(base_dir=temp_prompts_dir)
    with pytest.raises(FileNotFoundError, match="not found"):
        manager.get("claim_extraction", version="v99")


def test_prompt_caching(temp_prompts_dir):
    """Prompts are cached after first load."""
    manager = PromptManager(base_dir=temp_prompts_dir)

    # Load twice
    prompt1 = manager.get("claim_extraction", version="v1")
    prompt2 = manager.get("claim_extraction", version="v1")

    assert prompt1 == prompt2
    # Verify cache hit by checking method cache info
    assert manager.get.cache_info().hits == 1


def test_real_prompt_manager():
    """Test with real prompt templates (integration-ish test)."""
    manager = PromptManager()  # Uses default base_dir

    # Should find claim_extraction/v1.txt
    prompt = manager.get("claim_extraction", version="v1")
    assert len(prompt) > 100  # Should be a substantial prompt
    assert "quantitative claim" in prompt.lower()

    # Should have metadata
    metadata = manager.get_metadata("claim_extraction", version="v1")
    assert "created" in metadata
    assert "description" in metadata
