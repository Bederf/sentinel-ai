"""Tests for DWG converter service.

Tests ODA binary detection, conversion subprocess, timeout handling,
and graceful degradation when binary is not available.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.dwg_converter_service import (
    DWGConverterNotAvailable,
    DWGConverterService,
    DWGConversionError,
    get_dwg_converter_service,
)


class TestDWGConverterAvailability:
    """Test ODA binary detection."""

    def test_is_available_returns_false_when_binary_missing(self):
        """is_available() returns False when binary does not exist."""
        service = DWGConverterService()
        service._oda_path = "/nonexistent/path/ODAFileConverter"
        assert service.is_available() is False

    def test_is_available_returns_false_for_empty_path(self):
        """is_available() returns False for empty path."""
        service = DWGConverterService()
        service._oda_path = ""
        assert service.is_available() is False

    @patch("app.services.dwg_converter_service.Path")
    @patch("app.services.dwg_converter_service.os.access", return_value=True)
    def test_is_available_returns_true_when_binary_exists(self, mock_access, mock_path_cls):
        """is_available() returns True when binary exists and is executable."""
        mock_path_inst = MagicMock()
        mock_path_inst.exists.return_value = True
        mock_path_cls.return_value = mock_path_inst

        service = DWGConverterService()
        service._oda_path = "/usr/local/bin/ODAFileConverter"
        assert service.is_available() is True


class TestDWGConversion:
    """Test DWG to DXF conversion."""

    @pytest.mark.asyncio
    async def test_convert_raises_not_available_when_binary_missing(self):
        """convert_dwg_to_dxf raises DWGConverterNotAvailable when binary missing."""
        service = DWGConverterService()
        service._oda_path = "/nonexistent/ODAFileConverter"

        with pytest.raises(DWGConverterNotAvailable) as exc_info:
            await service.convert_dwg_to_dxf(b"fake dwg data", "test.dwg")

        assert "ODA File Converter not found" in str(exc_info.value)
        assert "test.dwg" not in str(exc_info.value)  # filename not leaked in error

    @pytest.mark.asyncio
    @patch("app.services.dwg_converter_service.shutil.rmtree")
    @patch("app.services.dwg_converter_service.asyncio.create_subprocess_exec")
    @patch.object(DWGConverterService, "is_available", return_value=True)
    async def test_convert_with_successful_subprocess(self, mock_available, mock_subprocess, mock_rmtree):
        """Successful conversion reads DXF output from temp directory."""
        # Mock subprocess
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"OK", b"")
        mock_proc.returncode = 0
        mock_subprocess.return_value = mock_proc

        service = DWGConverterService()

        # We need to mock file operations too
        with (
            patch("builtins.open", create=True) as mock_open,
            patch("app.services.dwg_converter_service.tempfile.mkdtemp") as mock_mkdtemp,
            patch("app.services.dwg_converter_service.os.path.exists") as mock_exists,
            patch("app.services.dwg_converter_service.os.listdir") as mock_listdir,
        ):
            mock_mkdtemp.side_effect = ["/tmp/dwg_in_xxx", "/tmp/dwg_out_xxx"]
            mock_exists.return_value = True

            # Mock file read for output
            mock_file = MagicMock()
            mock_file.__enter__ = MagicMock(return_value=mock_file)
            mock_file.__exit__ = MagicMock(return_value=False)
            mock_file.read.return_value = b"DXF content here"
            mock_file.write = MagicMock()
            mock_open.return_value = mock_file

            result = await service.convert_dwg_to_dxf(b"DWG data", "floor.dwg")
            assert result == b"DXF content here"

    @pytest.mark.asyncio
    @patch("app.services.dwg_converter_service.shutil.rmtree")
    @patch("app.services.dwg_converter_service.asyncio.create_subprocess_exec")
    @patch.object(DWGConverterService, "is_available", return_value=True)
    async def test_convert_handles_subprocess_failure(self, mock_available, mock_subprocess, mock_rmtree):
        """Conversion raises DWGConversionError when subprocess returns non-zero."""
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"Error: corrupt file")
        mock_proc.returncode = 1
        mock_subprocess.return_value = mock_proc

        service = DWGConverterService()

        with (
            patch("builtins.open", create=True),
            patch("app.services.dwg_converter_service.tempfile.mkdtemp") as mock_mkdtemp,
        ):
            mock_mkdtemp.side_effect = ["/tmp/dwg_in_xxx", "/tmp/dwg_out_xxx"]

            with pytest.raises(DWGConversionError, match="ODA converter failed"):
                await service.convert_dwg_to_dxf(b"DWG data", "corrupt.dwg")

    @pytest.mark.asyncio
    @patch("app.services.dwg_converter_service.shutil.rmtree")
    @patch("app.services.dwg_converter_service.asyncio.create_subprocess_exec")
    @patch.object(DWGConverterService, "is_available", return_value=True)
    async def test_convert_handles_timeout(self, mock_available, mock_subprocess, mock_rmtree):
        """Conversion raises DWGConversionError on timeout."""
        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = asyncio.TimeoutError()
        mock_proc.kill = MagicMock()
        # After kill, communicate returns empty
        mock_proc.communicate = AsyncMock(side_effect=[asyncio.TimeoutError(), (b"", b"")])
        mock_subprocess.return_value = mock_proc

        service = DWGConverterService()
        service.CONVERSION_TIMEOUT = 0.01  # Very short timeout for test

        with (
            patch("builtins.open", create=True),
            patch("app.services.dwg_converter_service.tempfile.mkdtemp") as mock_mkdtemp,
            patch("app.services.dwg_converter_service.asyncio.wait_for") as mock_wait,
        ):
            mock_mkdtemp.side_effect = ["/tmp/dwg_in_xxx", "/tmp/dwg_out_xxx"]
            mock_wait.side_effect = asyncio.TimeoutError()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))

            with pytest.raises(DWGConversionError, match="timed out"):
                await service.convert_dwg_to_dxf(b"DWG data", "huge.dwg")


class TestDWGConverterFactory:
    """Test singleton factory."""

    def test_get_dwg_converter_service_returns_instance(self):
        """Factory returns a DWGConverterService instance."""
        service = get_dwg_converter_service()
        assert isinstance(service, DWGConverterService)

    def test_get_dwg_converter_service_returns_same_instance(self):
        """Factory returns the same singleton instance."""
        service1 = get_dwg_converter_service()
        service2 = get_dwg_converter_service()
        assert service1 is service2
