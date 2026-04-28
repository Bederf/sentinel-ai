"""
phyphox Screenshot Analyzer (Phase 41-03)

Uses Claude Vision API to extract vibration/audio spectrum data from phyphox app screenshots.
Technicians capture 10-second recordings in phyphox, screenshot the spectrum graph,
and send via Sentry/Telegram. This service extracts peak frequencies and amplitudes.

Reference: backend/app/services/vision_service.py for Vision API patterns
"""

import base64
import json
import logging
from typing import Any

from app.services.model_gateway import model_gateway
from app.utils.calm_harness import calm_error_legacy

logger = logging.getLogger(__name__)


class PhyphoxAnalyzer:
    """Extract vibration/audio data from phyphox screenshots using Vision API."""

    async def analyze_spectrum_screenshot(
        self,
        image_data: bytes,
        measurement_type: str,  # "vibration" or "audio"
        equipment_id: str,
        media_type: str = "image/jpeg",
    ) -> dict[str, Any]:
        """
        Extract spectrum data from phyphox screenshot.

        Args:
            image_data: Screenshot image bytes (JPEG/PNG)
            measurement_type: "vibration" (acceleration) or "audio" (sound)
            equipment_id: Equipment being measured
            media_type: Image MIME type

        Returns:
            Extracted spectrum features
        """
        base64_image = base64.standard_b64encode(image_data).decode("utf-8")

        prompt = self._get_extraction_prompt(measurement_type)

        try:
            response_text = await model_gateway.call(
                task_class="light",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": base64_image},
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=1024,
                source="phyphox_screenshot_analysis",
            )

            # Parse structured response
            return self._parse_response(response_text, measurement_type)

        except Exception as e:
            logger.error(f"phyphox screenshot analysis failed: {e}")
            error_result = calm_error_legacy(e, tool_name="phyphox_screenshot")
            return {
                "measurement_type": measurement_type,
                "source": "screenshot",
                "error": error_result["error"],
                "confidence": 0.0,
            }

    def _get_extraction_prompt(self, measurement_type: str) -> str:
        """Get Vision API prompt for data extraction."""
        if measurement_type == "vibration":
            return """Analyze this phyphox acceleration spectrum screenshot.
Extract and return as JSON:
{
  "measurement_type": "vibration",
  "peak_frequencies_hz": [list of dominant peak frequencies],
  "peak_amplitudes_ms2": [corresponding amplitudes in m/s²],
  "rms_acceleration_ms2": <overall RMS if visible>,
  "frequency_range_hz": {"min": <x-axis min>, "max": <x-axis max>},
  "dominant_frequency_hz": <single highest peak>,
  "dominant_amplitude_ms2": <amplitude of highest peak>,
  "spectrum_shape": "narrowband|broadband|harmonic|random",
  "quality_assessment": "good|acceptable|poor",
  "quality_issues": [list any issues like "noisy", "clipped", "short duration"],
  "confidence": 0.0-1.0
}
Only return valid JSON, no other text."""

        else:  # audio
            return """Analyze this phyphox audio spectrum screenshot.
Extract and return as JSON:
{
  "measurement_type": "audio",
  "peak_frequencies_hz": [list of dominant peak frequencies],
  "peak_amplitudes_db": [corresponding amplitudes in dB],
  "overall_level_db": <overall sound level if visible>,
  "frequency_range_hz": {"min": <x-axis min>, "max": <x-axis max>},
  "dominant_frequency_hz": <single highest peak>,
  "dominant_amplitude_db": <amplitude of highest peak>,
  "spectrum_shape": "narrowband|broadband|harmonic|tonal|random",
  "quality_assessment": "good|acceptable|poor",
  "quality_issues": [list any issues],
  "confidence": 0.0-1.0
}
Only return valid JSON, no other text."""

    def _parse_response(self, response_text: str, measurement_type: str) -> dict[str, Any]:
        """Parse Vision API response to structured data."""
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                data = json.loads(response_text[json_start:json_end])
                data["source"] = "screenshot"
                return data
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON from Vision response: {e}")

        return {
            "measurement_type": measurement_type,
            "source": "screenshot",
            "error": "Failed to parse spectrum data",
            "raw_response": response_text[:500],
            "confidence": 0.0,
        }


# Singleton instance
_analyzer_instance: PhyphoxAnalyzer | None = None


def get_phyphox_analyzer() -> PhyphoxAnalyzer:
    """Get or create the singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = PhyphoxAnalyzer()
    return _analyzer_instance
