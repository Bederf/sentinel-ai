"""DWG Converter Service - Convert AutoCAD DWG files to DXF via ODA File Converter.

Wraps the ODA File Converter binary for DWG→DXF conversion. Gracefully degrades
when ODA is not installed — DXF files still work via the existing parser.

ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter
Free for non-commercial use, handles DWG R12 through 2024.
"""

import asyncio
import logging
import os
import tempfile
import shutil
from pathlib import Path

from app.config.settings import settings

logger = logging.getLogger(__name__)


class DWGConverterNotAvailable(Exception):
    """Raised when ODA File Converter binary is not installed or not executable."""

    def __init__(self, path: str = ""):
        self.path = path
        msg = (
            f"ODA File Converter not found at '{path}'. "
            "DWG files require the ODA File Converter binary. "
            "Install from https://www.opendesign.com/guestfiles/oda_file_converter "
            "or use DXF files directly (no conversion needed)."
        )
        super().__init__(msg)


class DWGConversionError(Exception):
    """Raised when DWG to DXF conversion fails."""

    pass


class DWGConverterService:
    """Convert DWG files to DXF using ODA File Converter.

    Singleton service that wraps the ODA binary. When the binary is not
    available, raises DWGConverterNotAvailable with a helpful message.
    DXF files bypass this service entirely.
    """

    # Default path for ODA binary
    DEFAULT_ODA_PATH = "/usr/local/bin/ODAFileConverter"

    # Conversion timeout in seconds
    CONVERSION_TIMEOUT = 30

    def __init__(self):
        """Initialize converter service."""
        self._oda_path = getattr(settings, "oda_converter_path", "") or self.DEFAULT_ODA_PATH

    def is_available(self) -> bool:
        """Check if ODA File Converter binary exists and is executable.

        Returns:
            True if the ODA binary is available, False otherwise.
        """
        if not self._oda_path:
            return False
        path = Path(self._oda_path)
        return path.is_file() and os.access(str(path), os.X_OK)

    async def convert_dwg_to_dxf(self, dwg_bytes: bytes, filename: str) -> bytes:
        """Convert DWG file bytes to DXF format.

        Uses ODA File Converter subprocess for the conversion. Creates temporary
        directories for input/output and cleans up afterwards.

        Args:
            dwg_bytes: Raw DWG file content.
            filename: Original filename (used for temp file naming).

        Returns:
            DXF file content as bytes.

        Raises:
            DWGConverterNotAvailable: If ODA binary is not installed.
            DWGConversionError: If conversion fails or times out.
        """
        if not self.is_available():
            raise DWGConverterNotAvailable(self._oda_path)

        input_dir = None
        output_dir = None

        try:
            # Create temp directories for ODA converter
            input_dir = tempfile.mkdtemp(prefix="dwg_in_")
            output_dir = tempfile.mkdtemp(prefix="dwg_out_")

            # Write DWG to input directory
            safe_name = Path(filename).stem + ".dwg"
            input_path = os.path.join(input_dir, safe_name)
            with open(input_path, "wb") as f:
                f.write(dwg_bytes)

            # Run ODA converter
            # ODA args: input_dir output_dir output_version output_type recurse audit
            # ACAD2018 = AutoCAD 2018 DXF format, 1 = DXF ASCII, 0 = no recurse, 1 = audit
            cmd = [
                self._oda_path,
                input_dir,
                output_dir,
                "ACAD2018",
                "DXF",
                "0",
                "1",
            ]

            logger.info(f"Converting DWG to DXF: {filename}")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.CONVERSION_TIMEOUT,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                raise DWGConversionError(f"DWG conversion timed out after {self.CONVERSION_TIMEOUT}s for {filename}")

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                raise DWGConversionError(f"ODA converter failed (exit {process.returncode}): {error_msg}")

            # Find output DXF file
            expected_output = os.path.join(output_dir, Path(filename).stem + ".dxf")
            if not os.path.exists(expected_output):
                # Try to find any DXF in output dir
                dxf_files = [f for f in os.listdir(output_dir) if f.lower().endswith(".dxf")]
                if not dxf_files:
                    raise DWGConversionError(f"No DXF output produced for {filename}")
                expected_output = os.path.join(output_dir, dxf_files[0])

            with open(expected_output, "rb") as f:
                dxf_bytes = f.read()

            logger.info(f"DWG conversion complete: {filename} -> {len(dxf_bytes)} bytes DXF")
            return dxf_bytes

        except (DWGConverterNotAvailable, DWGConversionError):
            raise
        except Exception as e:
            raise DWGConversionError(f"Unexpected error converting {filename}: {e}")
        finally:
            # Clean up temp directories
            for d in [input_dir, output_dir]:
                if d:
                    try:
                        shutil.rmtree(d)
                    except Exception:
                        pass


# Singleton
_dwg_converter_service = None


def get_dwg_converter_service() -> DWGConverterService:
    """Get or create singleton DWG converter service."""
    global _dwg_converter_service
    if _dwg_converter_service is None:
        _dwg_converter_service = DWGConverterService()
    return _dwg_converter_service
