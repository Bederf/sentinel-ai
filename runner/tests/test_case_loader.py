"""Tests for CaseLoader — file validation, path traversal, size limits."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.case_loader import (
    BLOCKED_EXTENSIONS,
    CaseLoader,
    HARD_CAP_BYTES,
    SOFT_CAP_BYTES,
)


class TestLoadCase:
    """Test case loading from filesystem."""

    def test_load_valid_case(self, mock_case_dir: Path, tmp_path: Path) -> None:
        """Valid case with manifest and evidence files loads correctly."""
        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        result = loader.load_case("TEST001")

        assert result["case_id"] == "TEST001"
        assert result["manifest"]["case_id"] == "TEST001"
        assert len(result["evidence_files"]) == 4  # .json, .csv, .pdf, .txt
        assert len(result["blocked_files"]) == 0

    def test_load_case_missing_manifest(self, tmp_path: Path) -> None:
        """Case without manifest.json raises FileNotFoundError."""
        case_dir = tmp_path / "cases" / "NO_MANIFEST"
        case_dir.mkdir(parents=True)

        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        with pytest.raises(FileNotFoundError, match="manifest.json not found"):
            loader.load_case("NO_MANIFEST")

    def test_load_case_nonexistent(self, tmp_path: Path) -> None:
        """Nonexistent case raises FileNotFoundError."""
        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        with pytest.raises(FileNotFoundError, match="Case directory not found"):
            loader.load_case("DOESNOTEXIST")


class TestFileTypeValidation:
    """Test file type allow/block policy."""

    def test_allowed_file_types(self, tmp_path: Path) -> None:
        """Allowed extensions pass through."""
        loader = CaseLoader(cases_dir=str(tmp_path))
        files = [
            tmp_path / "data.json",
            tmp_path / "log.csv",
            tmp_path / "report.pdf",
            tmp_path / "notes.txt",
            tmp_path / "image.png",
        ]
        for f in files:
            f.touch()

        allowed, blocked = loader.validate_file_types(files)
        assert len(allowed) == 5
        assert len(blocked) == 0

    def test_blocked_file_types(self, tmp_path: Path) -> None:
        """Blocked extensions (.exe, .zip, .sh) are separated."""
        loader = CaseLoader(cases_dir=str(tmp_path))
        files = [
            tmp_path / "malware.exe",
            tmp_path / "archive.zip",
            tmp_path / "script.sh",
            tmp_path / "library.dll",
            tmp_path / "good.json",
        ]
        for f in files:
            f.touch()

        allowed, blocked = loader.validate_file_types(files)
        assert len(allowed) == 1  # only .json
        assert len(blocked) == 4  # .exe, .zip, .sh, .dll

    def test_unknown_extension_blocked(self, tmp_path: Path) -> None:
        """Unknown extensions are treated as blocked for safety."""
        loader = CaseLoader(cases_dir=str(tmp_path))
        files = [tmp_path / "mystery.xyz"]
        for f in files:
            f.touch()

        allowed, blocked = loader.validate_file_types(files)
        assert len(allowed) == 0
        assert len(blocked) == 1


class TestPathTraversal:
    """Test path traversal protection."""

    def test_path_traversal_rejected(self, tmp_path: Path) -> None:
        """case_id='../etc' is rejected as path traversal."""
        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        with pytest.raises(ValueError, match="Path traversal detected"):
            loader.load_case("../etc")

    def test_path_traversal_double_dots(self, tmp_path: Path) -> None:
        """case_id='../../root' is rejected."""
        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        with pytest.raises((ValueError, FileNotFoundError)):
            loader.load_case("../../root")


class TestSizeLimits:
    """Test case size limit detection."""

    def test_size_under_limits(self, mock_case_dir: Path, tmp_path: Path) -> None:
        """Small case is within all limits."""
        loader = CaseLoader(cases_dir=str(tmp_path / "cases"))
        result = loader.check_size_limits(mock_case_dir)
        assert result["total_bytes"] > 0
        assert result["over_soft"] is False
        assert result["over_hard"] is False

    def test_size_over_soft_cap(self, tmp_path: Path) -> None:
        """Case over 500MB soft cap is flagged."""
        case_dir = tmp_path / "big_case"
        case_dir.mkdir()

        # Create a file that pushes over soft cap (sparse file for speed)
        big_file = case_dir / "big.bin"
        with open(big_file, "wb") as f:
            f.seek(SOFT_CAP_BYTES + 1)
            f.write(b"\0")

        loader = CaseLoader(cases_dir=str(tmp_path))
        result = loader.check_size_limits(case_dir)
        assert result["over_soft"] is True
