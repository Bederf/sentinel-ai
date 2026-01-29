"""Service for matching BMS points to CAFM assets."""

import re
from typing import List, Dict, Optional, Tuple
from difflib import SequenceMatcher

from app.models.integration import (
    AssetMatchResult, BulkMatchResult, MatchConfidence,
    PointAssetMappingCreate,
)


class PointMatcherService:
    """Service for matching BMS point IDs to CAFM assets."""

    # Common patterns for extracting asset ID from point names
    EXTRACTION_PATTERNS = [
        # Pattern: Controller/AssetID.Parameter (Honeywell)
        # NAE01/AHU-L12-001.SAT → AHU-L12-001
        r'^[A-Z0-9]+/([A-Z]+-[A-Z0-9-]+)\.',

        # Pattern: Building.Floor.Asset (Siemens)
        # Building1.Floor12.AHU_001_SAT → AHU_001
        r'[A-Za-z]+\d*\.[A-Za-z]+\d*\.([A-Z]+_\d+)',

        # Pattern: AssetID/Parameter (JCI)
        # AHU-12-1/SAT → AHU-12-1
        r'^([A-Z]+-\d+-\d+)/',

        # Pattern: System/AssetID.Parameter
        # BMS/AHU/L12/001/SAT → AHU-L12-001 (needs special handling)
        r'/([A-Z]+)/([A-Z]?\d+)/(\d+)/',

        # Pattern: Simple AssetID.Parameter
        # CH-001.CHWST → CH-001
        r'^([A-Z]+-\d+)\.',

        # Pattern: AssetID_Parameter
        # AHU_L12_001_SAT → AHU_L12_001
        r'^([A-Z]+_[A-Z]?\d+_\d+)_',
    ]

    # Parameter name patterns
    PARAMETER_PATTERNS = {
        'SAT': 'supply_air_temp',
        'RAT': 'return_air_temp',
        'OAT': 'outside_air_temp',
        'CHW': 'chilled_water',
        'CHWST': 'chw_supply_temp',
        'CHWRT': 'chw_return_temp',
        'FAN': 'fan_speed',
        'FanSpd': 'fan_speed',
        'VLV': 'valve_position',
        'Status': 'status',
        'Run': 'run_status',
        'Alarm': 'alarm',
        'DP': 'differential_pressure',
        'FILT_DP': 'filter_dp',
        'Amps': 'current',
        'kW': 'power',
        'Load': 'load_percent',
    }

    def extract_asset_id(self, point_id: str) -> Tuple[Optional[str], Optional[str]]:
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
                asset_id = asset_id.replace('_', '-').upper()

                # Extract parameter from remaining part
                param = self._extract_parameter(point_id, asset_id)

                return asset_id, param

        # Fallback: try to find asset-like pattern anywhere
        fallback = re.search(r'([A-Z]{2,4}[-_][A-Z]?\d+[-_]?\d*)', point_id, re.IGNORECASE)
        if fallback:
            asset_id = fallback.group(1).replace('_', '-').upper()
            param = self._extract_parameter(point_id, asset_id)
            return asset_id, param

        return None, None

    def _extract_parameter(self, point_id: str, asset_id: str) -> Optional[str]:
        """Extract parameter name from point ID after asset ID."""
        # Find what comes after the asset ID
        idx = point_id.upper().find(asset_id.upper())
        if idx >= 0:
            remainder = point_id[idx + len(asset_id):]
            # Clean up separators
            remainder = re.sub(r'^[./_]', '', remainder)
            if remainder:
                # Check against known patterns
                for pattern, name in self.PARAMETER_PATTERNS.items():
                    if pattern.upper() in remainder.upper():
                        return name
                # Return raw if no match
                return remainder.split('.')[0].split('/')[0]
        return None

    def match_to_cafm(
        self,
        extracted_id: str,
        cafm_assets: List[Dict[str, str]],
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
                bms_point_id='',
                extracted_asset_id='',
                confidence=MatchConfidence.UNMATCHED,
            )

        extracted_upper = extracted_id.upper().strip()

        # Try exact match first
        for asset in cafm_assets:
            tag = asset.get('asset_tag', '').upper().strip()
            if tag == extracted_upper:
                return AssetMatchResult(
                    bms_point_id='',
                    extracted_asset_id=extracted_id,
                    cafm_asset_id=asset.get('asset_tag'),
                    cafm_asset_description=asset.get('description'),
                    confidence=MatchConfidence.EXACT,
                )

        # Try fuzzy match
        best_match = None
        best_ratio = 0.0
        alternatives = []

        for asset in cafm_assets:
            tag = asset.get('asset_tag', '').upper().strip()

            # Calculate similarity
            ratio = SequenceMatcher(None, extracted_upper, tag).ratio()

            if ratio > fuzzy_threshold:
                alternatives.append({
                    'asset_tag': asset.get('asset_tag'),
                    'description': asset.get('description'),
                    'similarity': round(ratio, 2),
                })

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = asset

        # Sort alternatives by similarity
        alternatives.sort(key=lambda x: x['similarity'], reverse=True)

        if best_match and best_ratio > fuzzy_threshold:
            return AssetMatchResult(
                bms_point_id='',
                extracted_asset_id=extracted_id,
                cafm_asset_id=best_match.get('asset_tag'),
                cafm_asset_description=best_match.get('description'),
                confidence=MatchConfidence.FUZZY,
                alternatives=alternatives[:5],  # Top 5 alternatives
            )

        return AssetMatchResult(
            bms_point_id='',
            extracted_asset_id=extracted_id,
            confidence=MatchConfidence.UNMATCHED,
            alternatives=alternatives[:5],
        )

    def bulk_match(
        self,
        point_ids: List[str],
        cafm_assets: List[Dict[str, str]],
    ) -> BulkMatchResult:
        """
        Match multiple BMS points to CAFM assets.

        Args:
            point_ids: List of BMS point IDs
            cafm_assets: List of CAFM assets

        Returns:
            BulkMatchResult with all matches and statistics
        """
        matches: List[AssetMatchResult] = []
        exact_count = 0
        fuzzy_count = 0
        unmatched_count = 0

        # Cache extraction results to avoid re-processing same assets
        extraction_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

        unique_points = list(set(point_ids))

        for point_id in unique_points:
            # Extract asset ID
            if point_id not in extraction_cache:
                extraction_cache[point_id] = self.extract_asset_id(point_id)

            extracted_id, param = extraction_cache[point_id]

            if not extracted_id:
                matches.append(AssetMatchResult(
                    bms_point_id=point_id,
                    extracted_asset_id='',
                    confidence=MatchConfidence.UNMATCHED,
                ))
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
