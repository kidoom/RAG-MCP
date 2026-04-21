"""Example integration test demonstrating multi-component testing.

Integration tests verify that multiple components work together correctly.
"""

import pytest
from pathlib import Path


@pytest.mark.integration
class TestIntegrationExample:
    """Example integration test class."""

    def test_project_structure_valid(self, project_root):
        """Verify project structure matches specification."""
        # Check key directories exist
        required_dirs = [
            "src",
            "src/core",
            "src/libs",
            "src/ingestion",
            "src/mcp_server",
            "config",
            "tests",
            "tests/unit",
            "tests/integration",
            "tests/e2e",
        ]
        for dir_name in required_dirs:
            dir_path = project_root / dir_name
            assert dir_path.exists(), f"Missing required directory: {dir_name}"
            assert dir_path.is_dir()

    def test_config_files_exist(self, project_root):
        """Verify configuration files are present."""
        config_dir = project_root / "config"
        required_files = [
            "settings.yaml",
            "prompts/chunk_refinement.txt",
            "prompts/image_captioning.txt",
            "prompts/rerank.txt",
        ]
        for file_name in required_files:
            file_path = config_dir / file_name
            assert file_path.exists(), f"Missing config file: {file_name}"

    def test_source_files_exist(self, project_root):
        """Verify core source files are present."""
        src_dir = project_root / "src"
        required_modules = [
            "core/__init__.py",
            "libs/__init__.py",
            "ingestion/__init__.py",
            "mcp_server/__init__.py",
        ]
        for module in required_modules:
            module_path = src_dir / module
            assert module_path.exists(), f"Missing source module: {module}"

    def test_pytest_config_valid(self, project_root):
        """Verify pytest configuration is valid."""
        pyproject = project_root / "pyproject.toml"
        assert pyproject.exists()
        
        content = pyproject.read_text()
        assert "[tool.pytest.ini_options]" in content
        assert "testpaths = [\"tests\"]" in content
        assert "markers" in content
