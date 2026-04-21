"""Pytest configuration and shared fixtures for the entire test suite."""

import pytest
import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, Any

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ============================================================================
# Pytest Configurations
# ============================================================================

def pytest_configure(config):
    """Register custom markers for test categorization."""
    config.addinivalue_line(
        "markers",
        "unit: mark test as a unit test (isolated component)"
    )
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (multi-component)"
    )
    config.addinivalue_line(
        "markers",
        "e2e: mark test as an end-to-end test (full workflow)"
    )
    config.addinivalue_line(
        "markers",
        "slow: mark test as slow (e.g., real LLM calls)"
    )


# ============================================================================
# Shared Fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir():
    """Create a temporary directory for test data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def project_root():
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def config_dir(project_root):
    """Return the config directory path."""
    return project_root / "config"


@pytest.fixture
def test_data_dir(project_root):
    """Return the test data directory (for E2E tests)."""
    test_data = project_root / "tests" / "data"
    test_data.mkdir(exist_ok=True)
    return test_data


@pytest.fixture
def mock_settings():
    """Provide mock settings for testing."""
    return {
        "llm": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.3,
        },
        "embedding": {
            "provider": "openai",
            "model": "text-embedding-3-small",
        },
        "vector_store": {
            "provider": "chroma",
            "collection_name": "test_collection",
        },
        "retrieval": {
            "top_k": 5,
            "rerank": False,
        },
    }
