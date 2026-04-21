"""Example unit test demonstrating pytest framework usage.

This test verifies basic pytest setup and fixtures.
Actual tests will be added in subsequent tasks (A3, B1, etc.).
"""

import pytest


@pytest.mark.unit
class TestPytestSetup:
    """Verify pytest framework is properly configured."""

    def test_pytest_installed(self):
        """Test that pytest is installed and working."""
        import pytest
        assert pytest.__version__
        assert len(pytest.__version__) > 0

    def test_fixtures_available(self, mock_settings):
        """Test that fixtures are properly injected."""
        assert mock_settings is not None
        assert "llm" in mock_settings
        assert mock_settings["llm"]["provider"] == "openai"

    def test_project_root_fixture(self, project_root):
        """Test that project_root fixture works."""
        assert project_root.exists()
        assert (project_root / "src").exists()
        assert (project_root / "tests").exists()

    def test_temp_data_dir_fixture(self, temp_data_dir):
        """Test that temporary directory fixture works."""
        from pathlib import Path
        temp_path = Path(temp_data_dir)
        assert temp_path.exists()
        assert temp_path.is_dir()

    def test_multiple_fixtures(self, mock_settings, project_root, temp_data_dir):
        """Test that multiple fixtures can be combined."""
        assert mock_settings is not None
        assert project_root.exists()
        from pathlib import Path
        assert Path(temp_data_dir).exists()


@pytest.mark.unit
def test_marker_applied():
    """Test that pytest markers are working."""
    assert True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
