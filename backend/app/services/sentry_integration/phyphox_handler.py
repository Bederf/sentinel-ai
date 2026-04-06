"""
Sentry phyphox Integration Handler (Phase 41-03)

Handle phyphox data received via Sentry/Telegram.
Integrates screenshot analysis (Vision API) and CSV parsing.
Provides technician instructions and anomaly detection.

Reference: backend/app/services/sentry_integration/ocr_correction_handler.py
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PhyphoxHandler:
    """Handle phyphox data from Sentry/Telegram."""

    def __init__(self):
        # Lazy import to avoid circular dependencies
        self._analyzer = None
        self._parser = None

    @property
    def analyzer(self):
        """Lazy load PhyphoxAnalyzer."""
        if self._analyzer is None:
            from app.services.phyphox_analyzer import PhyphoxAnalyzer

            self._analyzer = PhyphoxAnalyzer()
        return self._analyzer

    @property
    def parser(self):
        """Lazy load PhyphoxParser."""
        if self._parser is None:
            from app.services.phyphox_parser import PhyphoxParser

            self._parser = PhyphoxParser()
        return self._parser

    async def process_phyphox_data(
        self,
        file_data: bytes,
        filename: str,
        equipment_id: str,
        service_record_id: str | None = None,
        measurement_type: str = "vibration",
    ) -> dict[str, Any]:
        """
        Process phyphox screenshot or export file.

        Args:
            file_data: File content (image or CSV/JSON)
            filename: Original filename
            equipment_id: Equipment being measured
            service_record_id: Optional link to service record
            measurement_type: "vibration" or "audio"

        Returns:
            Processed sensor data with anomaly analysis
        """
        # Determine input type
        filename_lower = filename.lower()
        is_image = filename_lower.endswith((".jpg", ".jpeg", ".png", ".webp"))

        if is_image:
            # Screenshot -> Vision API extraction
            logger.info(f"Processing phyphox screenshot for equipment {equipment_id}")

            # Detect media type
            if filename_lower.endswith(".png"):
                media_type = "image/png"
            elif filename_lower.endswith(".webp"):
                media_type = "image/webp"
            else:
                media_type = "image/jpeg"

            result = await self.analyzer.analyze_spectrum_screenshot(
                file_data, measurement_type, equipment_id, media_type
            )
        else:
            # CSV/JSON -> Direct parsing
            logger.info(f"Processing phyphox export {filename} for equipment {equipment_id}")
            result = self.parser.parse_export(file_data, filename)

        # Add metadata
        result["equipment_id"] = equipment_id
        result["service_record_id"] = service_record_id
        result["filename"] = filename

        # Run anomaly detection
        anomalies = await self._detect_anomalies(result, measurement_type)
        result["anomalies"] = anomalies

        return result

    async def _detect_anomalies(self, data: dict[str, Any], measurement_type: str) -> dict[str, Any]:
        """Run anomaly detection on extracted data."""
        anomalies = {"detected": [], "severity": "normal", "confidence": 0.0}

        # Skip anomaly detection if we got an error
        if data.get("error"):
            return anomalies

        try:
            if measurement_type == "vibration":
                # Check for bearing defects
                from app.services.bearing_analyzer import BearingAnalyzer

                bearing_analyzer = BearingAnalyzer()
                bearing_result = bearing_analyzer.analyze(data)

                if bearing_result.get("defect_detected"):
                    anomalies["detected"].append(
                        {
                            "type": "bearing_defect",
                            "subtype": bearing_result.get("defect_type"),
                            "confidence": bearing_result.get("confidence", 0),
                            "frequency_hz": bearing_result.get("defect_frequency"),
                            "details": bearing_result.get("analysis_details", {}),
                        }
                    )

            elif measurement_type == "audio":
                # Check for engine knock
                from app.services.knock_detector import KnockDetector

                knock_detector = KnockDetector()
                knock_result = knock_detector.analyze(data)

                if knock_result.get("knock_detected"):
                    anomalies["detected"].append(
                        {
                            "type": "engine_knock",
                            "confidence": knock_result.get("confidence", 0),
                            "frequency_hz": knock_result.get("knock_frequency"),
                            "details": knock_result.get("analysis_details", {}),
                        }
                    )

        except ImportError as e:
            logger.warning(f"Anomaly detection not available: {e}")
        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")

        # Set overall severity
        if anomalies["detected"]:
            max_confidence = max(a["confidence"] for a in anomalies["detected"])
            anomalies["confidence"] = max_confidence
            if max_confidence > 0.8:
                anomalies["severity"] = "high"
            elif max_confidence > 0.5:
                anomalies["severity"] = "medium"
            else:
                anomalies["severity"] = "low"

        return anomalies

    def get_technician_instructions(
        self, measurement_type: str = "vibration", equipment_type: str | None = None
    ) -> str:
        """
        Get instructions to send to technician via Sentry.

        Args:
            measurement_type: Type of measurement ("vibration", "audio", "multi")
            equipment_type: Optional equipment type for specific guidance

        Returns:
            Formatted instructions string for Telegram
        """
        if measurement_type == "vibration":
            base = """📱 **Vibration Recording with phyphox**

1. Open phyphox app (free from app store)
2. Select **"Acceleration without g"** (under Raw Sensors)
3. **Fix phone rigidly to equipment frame** (tape or rubber band)
4. Press ▶️ to start recording
5. Wait 10 seconds
6. Press ⏹️ to stop
7. Take a **screenshot** of the graph
8. Send the screenshot here"""

            if equipment_type == "generator":
                base += """

⚙️ **Generator-specific:**
• Mount near alternator end bearing
• Record UNLOADED first, then LOADED
• For 1500 RPM: expect peaks at 25Hz (1x) and 50Hz (2x)
• New peaks or rising levels = potential issue"""

            elif equipment_type == "chiller":
                base += """

⚙️ **Chiller-specific:**
• Mount on compressor housing
• Record during steady-state operation
• Watch for peaks at compressor rotational frequency
• Rising broadband noise = bearing wear"""

            elif equipment_type == "pump":
                base += """

⚙️ **Pump-specific:**
• Mount on bearing housing
• Record at normal operating speed
• Check for 1x and 2x shaft frequency peaks
• Cavitation shows as broadband high-frequency noise"""

            base += """

💡 Tip: Phone must be fixed firmly - hand-held won't work"""
            return base

        elif measurement_type == "audio":
            return """🎤 **Audio Recording with phyphox**

1. Open phyphox app
2. Select **"Audio Spectrum"** (under Acoustics)
3. Hold phone 30cm from equipment
4. Press ▶️ to start recording
5. Wait 10 seconds
6. Press ⏹️ to stop
7. Take a **screenshot** of the spectrum graph
8. Send the screenshot here

⚙️ **What we're looking for:**
• Stable peaks at running speed harmonics = healthy
• Broadband noise increase = bearing wear
• New peaks appearing = developing fault

💡 Tip: Record in quiet area for cleaner results"""

        elif measurement_type == "multi":
            # Full diagnostic protocol
            return """🔧 **Full Generator Diagnostic (3 recordings)**

We'll do 3 quick tests. Fix phone to generator frame for all.

**Test 1: Vibration (Acceleration without g)**
1. Open phyphox → "Acceleration without g"
2. Record 10 sec → Screenshot → Send

**Test 2: Audio (Audio Spectrum)**
1. Open phyphox → "Audio Spectrum"
2. Record 10 sec → Screenshot → Send

**Test 3: Rotation (Gyroscope)**
1. Open phyphox → "Gyroscope"
2. Record 10 sec → Screenshot → Send

⚠️ If possible, do once UNLOADED then once with LOAD.

Send all screenshots and I'll analyze them together."""

        else:
            return """📱 **phyphox Recording**

1. Open phyphox app
2. Select appropriate experiment
3. Record for 10 seconds
4. Screenshot the result
5. Send here for analysis

Supported types: vibration, audio, multi"""


# Singleton instance
_handler_instance: PhyphoxHandler | None = None


def get_phyphox_handler() -> PhyphoxHandler:
    """Get or create the singleton handler instance."""
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = PhyphoxHandler()
    return _handler_instance
