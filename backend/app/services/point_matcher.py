"""Service for matching BMS points to CAFM assets."""

import re
from difflib import SequenceMatcher

from app.models.integration import (
    AssetMatchResult,
    BulkMatchResult,
    MatchConfidence,
    PointAssetMappingCreate,
)


class PointMatcherService:
    """Service for matching BMS point IDs to CAFM assets."""

    # Common patterns for extracting asset ID from point names
    EXTRACTION_PATTERNS = [
        # Pattern: S002-AssetID.Parameter (SENTINEL canonical — e.g. S002-FCU-003.status, S002-AHU-B1-001.health_score)
        # Must come first — more specific than the generic S002-site prefix pattern
        r"^(S002-(?:AHU|FCU|VAV|CHILLER|MTR|CT|DALI|LTG|ZONE|SENSOR|WEATHER|INV|GEN|BESS|PUMP)-[A-Z0-9-]+)",
        # Pattern: Controller/AssetID.Parameter (Honeywell)
        # NAE01/AHU-L12-001.SAT → AHU-L12-001
        r"^[A-Z0-9]+/([A-Z]+-[A-Z0-9-]+)\.",
        # Pattern: Building.Floor.Asset (Siemens)
        # Building1.Floor12.AHU_001_SAT → AHU_001
        r"[A-Za-z]+\d*\.[A-Za-z]+\d*\.([A-Z]+_\d+)",
        # Pattern: AssetID/Parameter (JCI)
        # AHU-12-1/SAT → AHU-12-1
        r"^([A-Z]+-\d+-\d+)/",
        # Pattern: System/AssetID.Parameter
        # BMS/AHU/L12/001/SAT → AHU-L12-001 (needs special handling)
        r"/([A-Z]+)/([A-Z]?\d+)/(\d+)/",
        # Pattern: AHU1/AHU2/AHU3 bare (SCADA/Siemens convention — maps to zone-specific S002 equipment)
        r"^(AHU\d+)\.",
        # Pattern: CHILLER/CHILLER1/CHILLER2 bare (maps to basement chillers)
        r"^(CHILLER\d?)\.",
        # Pattern: CT/CT1 bare (maps to basement cooling tower)
        r"^(CT\d?)\.",
        # Pattern: FCU01–FCU05 bare (maps to zone G FCUs 001–005)
        r"^(FCU0[1-5])\.",
        # Pattern: FCU06 bare (maps to L1 FCU 101)
        r"^(FCU06)\.",
        # Pattern: FCU07–FCU15 bare (maps to L1 FCUs 102–105)
        r"^(FCU0[7-9])\.",
        # Pattern: FCU10–FCU15 (second digit 0-5, first digit 1)
        r"^(FCU1[0-5])\.",
        # Pattern: FCU16–FCU20 bare (maps to L2 FCUs 201–205)
        r"^(FCU(?:1[6-9]|2[0-5]))\.",
        # Pattern: FCU21–FCU39 bare (maps to L3 FCUs 221–305)
        r"^(FCU(?:2[1-9]|[3-9]\d))\.",
        # Pattern: Simple AssetID.Parameter
        # CH-001.CHWST → CH-001  (must come AFTER FCU bare patterns to avoid false extraction)
        r"^([A-Z]+-\d+)\.",
        # Pattern: AssetID_Parameter
        # AHU_L12_001_SAT → AHU_L12_001
        r"^([A-Z]+_[A-Z]?\d+_\d+)_",
    ]

    # Maps bare SCADA asset IDs → S002-prefixed equipment codes
    # Used after extraction to normalize bare IDs to their physical zone assignments
    SCADA_NORMALIZATION_MAP = {
        # AHU: basement (B01), Level 2 (201), Rooftop (R01)
        # Note: codes must match equipment table (site-002)
        "AHU1": "S002-AHU-B01",
        "AHU2": "S002-AHU-201",
        "AHU3": "S002-AHU-R01",
        # CHILLER: basement B01
        "CHILLER": "S002-CHILLER-B01",
        "CHILLER1": "S002-CHILLER-B01",
        "CHILLER2": "S002-CHILLER-B01",
        # Cooling tower: basement B01, rooftop R01
        "CT": "S002-CT-B01",
        "CT1": "S002-CT-B01",
        "CT2": "S002-CT-R01",
    }

    # FCU zone mapping: FCU## → S002-FCU-{zone}{seq:03d}
    # G-zone: FCU01→001, FCU02→002, FCU03→003, FCU04→004, FCU05→005
    # L1-zone: FCU06→101, FCU07→102, ..., FCU15→105
    # L2-zone: FCU16→201, FCU17→202, ..., FCU20→205
    # L3-zone: FCU21-25 → S002-FCU-301..305 (equipment table has 301-305)
    FCU_NORMALIZATION_RANGES = [
        (1, 5, "G", 0),  # FCU01-05 → S002-FCU-001..005
        (6, 15, "L1", 100),  # FCU06-15 → S002-FCU-101..105
        (16, 20, "L2", 200),  # FCU16-20 → S002-FCU-201..205
        (21, 25, "L3", 300),  # FCU21-25 → S002-FCU-301..305
    ]

    # Parameter name patterns
    PARAMETER_PATTERNS = {
        "SAT": "supply_air_temp",
        "RAT": "return_air_temp",
        "OAT": "outside_air_temp",
        "CHW": "chilled_water",
        "CHWST": "chw_supply_temp",
        "CHWRT": "chw_return_temp",
        "FAN": "fan_speed",
        "FanSpd": "fan_speed",
        "VLV": "valve_position",
        "Status": "status",
        "Run": "run_status",
        "Alarm": "alarm",
        "DP": "differential_pressure",
        "FILT_DP": "filter_dp",
        "Amps": "current",
        "kW": "power",
        "Load": "load_percent",
    }

    def extract_asset_id(self, point_id: str) -> tuple[str | None, str | None]:
        """
        Extract asset ID and parameter name from BMS point ID.

        Returns:
            Tuple of (asset_id, parameter_name)
        """
        if not point_id:
            return None, None

        # Try each pattern
        for pattern in self.EXTRACTION_PATTERNS:
            match = re.search(pattern, point_id, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) >= 3:
                    # Multi-part pattern like BMS/AHU/L12/001
                    asset_id = f"{groups[0]}-{groups[1]}-{groups[2]}"
                else:
                    asset_id = groups[0]

                # Normalize: replace underscores with dashes, uppercase
                asset_id = asset_id.replace("_", "-").upper()

                # Normalize bare SCADA IDs to S002-prefixed equipment codes
                asset_id = self._normalize_scada_asset_id(asset_id)

                # Extract parameter from remaining part
                param = self._extract_parameter(point_id, asset_id)

                return asset_id, param

        # Fallback: try to find asset-like pattern anywhere
        fallback = re.search(r"([A-Z]{2,4}[-_][A-Z]?\d+[-_]?\d*)", point_id, re.IGNORECASE)
        if fallback:
            asset_id = fallback.group(1).replace("_", "-").upper()
            asset_id = self._normalize_scada_asset_id(asset_id)
            param = self._extract_parameter(point_id, asset_id)
            return asset_id, param

        return None, None

    def _normalize_scada_asset_id(self, asset_id: str) -> str:
        """Normalize a bare SCADA asset ID to its S002-prefixed equipment code."""
        if not asset_id:
            return asset_id

        # Already S002-prefixed — no normalization needed
        if asset_id.startswith("S002-"):
            return asset_id

        # Direct mapping for AHU/CHILLER/CT types
        if asset_id in self.SCADA_NORMALIZATION_MAP:
            return self.SCADA_NORMALIZATION_MAP[asset_id]

        # FCU range-based mapping
        if asset_id.startswith("FCU"):
            return self._normalize_fcu_asset_id(asset_id)

        # Unknown bare ID — return as-is (will remain unmatched)
        return asset_id

    def _normalize_fcu_asset_id(self, asset_id: str) -> str:
        """Normalize a bare FCU ID to its S002-prefixed equipment code."""
        # Extract the numeric suffix: FCU01 → 1, FCU21 → 21
        match = re.match(r"^FCU(\d+)$", asset_id, re.IGNORECASE)
        if not match:
            return asset_id

        num = int(match.group(1))

        for start, end, zone, offset in self.FCU_NORMALIZATION_RANGES:
            if start <= num <= end:
                seq = num - start + 1  # 1-based within range
                if zone == "G":
                    # G-zone: 001..005 (padded to 3 digits, no zone letter)
                    return f"S002-FCU-{seq:03d}"
                else:
                    # L1→101..105, L2→201..205, L3→301..305
                    return f"S002-FCU-{offset + seq}"

        return asset_id  # Unmapped FCU range

    def _extract_parameter(self, point_id: str, asset_id: str) -> str | None:
        """Extract parameter name from point ID after asset ID."""
        # Find what comes after the asset ID
        idx = point_id.upper().find(asset_id.upper())
        if idx >= 0:
            remainder = point_id[idx + len(asset_id) :]
            # Clean up separators
            remainder = re.sub(r"^[./_]", "", remainder)
            if remainder:
                # Check against known patterns
                for pattern, name in self.PARAMETER_PATTERNS.items():
                    if pattern.upper() in remainder.upper():
                        return name
                # Return raw if no match
                return remainder.split(".")[0].split("/")[0]
        return None

    def match_to_cafm(
        self,
        extracted_id: str,
        cafm_assets: list[dict[str, str]],
        fuzzy_threshold: float = 0.8,
    ) -> AssetMatchResult:
        """
        Match extracted asset ID to CAFM assets.

        Args:
            extracted_id: Extracted asset ID from BMS point
            cafm_assets: List of CAFM assets with 'asset_tag' and 'description'
            fuzzy_threshold: Minimum similarity for fuzzy match

        Returns:
            AssetMatchResult with match confidence and alternatives
        """
        if not extracted_id:
            return AssetMatchResult(
                bms_point_id="",
                extracted_asset_id="",
                confidence=MatchConfidence.UNMATCHED,
            )

        extracted_upper = extracted_id.upper().strip()

        # Try exact match first
        for asset in cafm_assets:
            tag = asset.get("asset_tag", "").upper().strip()
            if tag == extracted_upper:
                return AssetMatchResult(
                    bms_point_id="",
                    extracted_asset_id=extracted_id,
                    cafm_asset_id=asset.get("asset_tag"),
                    cafm_asset_description=asset.get("description"),
                    confidence=MatchConfidence.EXACT,
                )

        # Try fuzzy match
        best_match = None
        best_ratio = 0.0
        alternatives = []

        for asset in cafm_assets:
            tag = asset.get("asset_tag", "").upper().strip()

            # Calculate similarity
            ratio = SequenceMatcher(None, extracted_upper, tag).ratio()

            if ratio > fuzzy_threshold:
                alternatives.append(
                    {
                        "asset_tag": asset.get("asset_tag"),
                        "description": asset.get("description"),
                        "similarity": round(ratio, 2),
                    }
                )

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = asset

        # Sort alternatives by similarity
        alternatives.sort(key=lambda x: x["similarity"], reverse=True)

        if best_match and best_ratio > fuzzy_threshold:
            return AssetMatchResult(
                bms_point_id="",
                extracted_asset_id=extracted_id,
                cafm_asset_id=best_match.get("asset_tag"),
                cafm_asset_description=best_match.get("description"),
                confidence=MatchConfidence.FUZZY,
                alternatives=alternatives[:5],  # Top 5 alternatives
            )

        return AssetMatchResult(
            bms_point_id="",
            extracted_asset_id=extracted_id,
            confidence=MatchConfidence.UNMATCHED,
            alternatives=alternatives[:5],
        )

    def bulk_match(
        self,
        point_ids: list[str],
        cafm_assets: list[dict[str, str]],
    ) -> BulkMatchResult:
        """
        Match multiple BMS points to CAFM assets.

        Args:
            point_ids: List of BMS point IDs
            cafm_assets: List of CAFM assets

        Returns:
            BulkMatchResult with all matches and statistics
        """
        matches: list[AssetMatchResult] = []
        exact_count = 0
        fuzzy_count = 0
        unmatched_count = 0

        # Cache extraction results to avoid re-processing same assets
        extraction_cache: dict[str, tuple[str | None, str | None]] = {}

        unique_points = list(set(point_ids))

        for point_id in unique_points:
            # Extract asset ID
            if point_id not in extraction_cache:
                extraction_cache[point_id] = self.extract_asset_id(point_id)

            extracted_id, param = extraction_cache[point_id]

            if not extracted_id:
                matches.append(
                    AssetMatchResult(
                        bms_point_id=point_id,
                        extracted_asset_id="",
                        confidence=MatchConfidence.UNMATCHED,
                    )
                )
                unmatched_count += 1
                continue

            # Match to CAFM
            result = self.match_to_cafm(extracted_id, cafm_assets)
            result.bms_point_id = point_id
            result.parameter_name = param

            matches.append(result)

            if result.confidence == MatchConfidence.EXACT:
                exact_count += 1
            elif result.confidence == MatchConfidence.FUZZY:
                fuzzy_count += 1
            else:
                unmatched_count += 1

        return BulkMatchResult(
            total_points=len(unique_points),
            matched_exact=exact_count,
            matched_fuzzy=fuzzy_count,
            unmatched=unmatched_count,
            matches=matches,
        )

    def create_mapping(
        self,
        point_id: str,
        match_result: AssetMatchResult,
    ) -> PointAssetMappingCreate:
        """Create a point-asset mapping from match result."""
        return PointAssetMappingCreate(
            bms_point_id=point_id,
            extracted_asset_id=match_result.extracted_asset_id,
            cafm_asset_id=match_result.cafm_asset_id,
            parameter_name=match_result.parameter_name,
            match_confidence=match_result.confidence,
        )
