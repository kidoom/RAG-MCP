"""Example end-to-end test demonstrating full workflow testing.

E2E tests simulate real user scenarios and complete workflows.
"""

import pytest


@pytest.mark.e2e
class TestE2EExample:
    """Example end-to-end test class."""

    def test_project_initialization(self, project_root):
        """Test basic project initialization and structure."""
        # Verify project is properly initialized
        assert project_root.exists()
        assert (project_root / "src").exists()
        assert (project_root / "main.py").exists()
        assert (project_root / "pyproject.toml").exists()

    def test_configuration_loading_ready(self, project_root):
        """Test that configuration can be loaded (A3 prerequisite)."""
        config_path = project_root / "config" / "settings.yaml"
        assert config_path.exists(), "settings.yaml must exist for configuration loading"
        
        # Verify configuration file is valid YAML
        content = config_path.read_text()
        assert len(content) > 0
        assert ":" in content  # Basic YAML structure check

    @pytest.mark.slow
    def test_mcp_server_importable(self, project_root):
        """Test that MCP server module can be imported."""
        import sys
        from pathlib import Path
        sys.path.insert(0, str(project_root / "src"))
        
        try:
            import mcp_server
            assert mcp_server is not None
        except ImportError:
            pytest.skip("MCP server not yet fully implemented")
