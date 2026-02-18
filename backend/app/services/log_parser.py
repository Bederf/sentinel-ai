"""Service for parsing BMS log files."""

import csv
import io
import json
import re
import hashlib
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from app.models.integration import (
    FileFormat, Severity, AlarmState,
    FormatDetectionResult, ParseResult, ParsedAlarm, ParsedTrend,
    ParseValidationError, ParseValidationWarning,
    ColumnMapping,
)


class LogParserService:
    """Service for parsing and normalizing BMS log files."""

    # Common column name patterns for auto-detection
    TIMESTAMP_PATTERNS = ['time', 'timestamp', 'date', 'datetime', 'date/time', 'date_time']
    POINT_ID_PATTERNS = ['point', 'pointid', 'point_id', 'object', 'item', 'item reference', 'source']
    ALARM_CODE_PATTERNS = ['alarm type', 'alarmtype', 'type', 'event', 'eventtype', 'alarm_code', 'code']
    DESCRIPTION_PATTERNS = ['description', 'message', 'alarm message', 'text', 'messagetext']
    VALUE_PATTERNS = ['value', 'alarm value', 'reading', 'actual']
    THRESHOLD_PATTERNS = ['limit', 'threshold', 'setpoint', 'sp']
    SEVERITY_PATTERNS = ['priority', 'severity', 'level', 'importance']
    STATE_PATTERNS = ['status', 'state', 'condition']
    ACK_BY_PATTERNS = ['operator', 'user', 'ack by', 'acknowledged by', 'acknowledgedby']
    NOTES_PATTERNS = ['action', 'notes', 'comment', 'annotation', 'remarks']

    # Vendor detection patterns
    VENDOR_PATTERNS = {
        'honeywell': [r'NAE\d+/', r'\.SAT$', r'\.RAT$', r'EBI'],
        'siemens': [r'Building\d+\.Floor', r'Desigo'],
        'jci': [r'Metasys', r'/SAT$', r'/RAT$'],
        'schneider': [r'BMS/', r'EcoStruxure'],
    }

    # Date format patterns to try
    DATE_FORMATS = [
        '%Y-%m-%d %H:%M:%S',      # ISO: 2026-01-28 14:32:15
        '%Y-%m-%dT%H:%M:%S',      # ISO-T: 2026-01-28T14:32:15
        '%Y-%m-%dT%H:%M:%SZ',     # ISO-Z: 2026-01-28T14:32:15Z
        '%d/%m/%Y %H:%M:%S',      # SA: 28/01/2026 14:32:15
        '%d/%m/%Y %H:%M',         # SA short: 28/01/2026 14:32
        '%m/%d/%Y %H:%M:%S',      # US: 01/28/2026 14:32:15
        '%m/%d/%Y %I:%M:%S %p',   # US 12hr: 01/28/2026 02:32:15 PM
        '%d.%m.%Y %H:%M:%S',      # EU: 28.01.2026 14:32:15
        '%d-%m-%Y %H:%M:%S',      # Alt: 28-01-2026 14:32:15
    ]

    def detect_format(self, content: str, filename: str = "") -> FormatDetectionResult:
        """Auto-detect file format, delimiter, date format, and suggest column mappings."""

        # Detect file format from extension or content
        file_format = self._detect_file_format(content, filename)

        if file_format == FileFormat.JSON:
            return self._detect_json_format(content)

        # CSV/Excel - detect delimiter
        delimiter = self._detect_delimiter(content)

        # Parse to get columns and sample data
        rows = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))
        if not rows:
            raise ValueError("No data rows found in file")

        columns = list(rows[0].keys())

        # Detect date format from first few rows
        date_column = self._find_column(columns, self.TIMESTAMP_PATTERNS)
        date_format = "YYYY-MM-DD HH:MI:SS"
        date_start = None
        date_end = None

        if date_column:
            date_format, date_start, date_end = self._detect_date_format(
                [r.get(date_column, '') for r in rows[:100]]
            )

        # Detect vendor from point IDs
        point_column = self._find_column(columns, self.POINT_ID_PATTERNS)
        vendor = None
        if point_column:
            sample_points = [r.get(point_column, '') for r in rows[:50]]
            vendor = self._detect_vendor(sample_points)

        # Suggest column mappings
        suggested_mappings = self._suggest_mappings(columns)

        return FormatDetectionResult(
            file_format=file_format,
            delimiter=delimiter,
            date_format=date_format,
            vendor_pattern=vendor,
            columns=columns,
            row_count=len(rows),
            date_range_start=date_start,
            date_range_end=date_end,
            sample_rows=rows[:10],
            suggested_mappings=suggested_mappings,
        )

    def parse_alarms(
        self,
        content: str,
        mappings: List[ColumnMapping],
        date_format: str,
        delimiter: str = ',',
        timezone: str = 'Africa/Johannesburg',
    ) -> ParseResult:
        """Parse alarm log file using configured mappings."""

        rows = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))

        parsed_alarms: List[ParsedAlarm] = []
        errors: List[ParseValidationError] = []
        warnings: List[ParseValidationWarning] = []
        unmatched_points: set = set()

        # Build mapping lookup
        mapping_dict = {m.sentinel_field: m for m in mappings}

        for idx, row in enumerate(rows, start=1):
            try:
                alarm = self._parse_alarm_row(row, mapping_dict, date_format, idx)
                if alarm:
                    parsed_alarms.append(alarm)
                    if not alarm.asset_id:
                        unmatched_points.add(alarm.point_id)
            except ValueError as e:
                errors.append(ParseValidationError(
                    row=idx,
                    field='row',
                    message=str(e),
                    value=None
                ))

        return ParseResult(
            total_rows=len(rows),
            valid_rows=len(parsed_alarms),
            error_count=len(errors),
            warning_count=len(warnings),
            errors=errors,
            warnings=warnings,
            parsed_alarms=parsed_alarms,
            unmatched_points=list(unmatched_points),
        )

    def parse_trends(
        self,
        content: str,
        mappings: List[ColumnMapping],
        date_format: str,
        delimiter: str = ',',
    ) -> ParseResult:
        """Parse trend log file using configured mappings."""

        rows = list(csv.DictReader(io.StringIO(content), delimiter=delimiter))

        parsed_trends: List[ParsedTrend] = []
        errors: List[ParseValidationError] = []
        unmatched_points: set = set()

        mapping_dict = {m.sentinel_field: m for m in mappings}

        for idx, row in enumerate(rows, start=1):
            try:
                trend = self._parse_trend_row(row, mapping_dict, date_format, idx)
                if trend:
                    parsed_trends.append(trend)
                    if not trend.asset_id:
                        unmatched_points.add(trend.point_id)
            except ValueError as e:
                errors.append(ParseValidationError(
                    row=idx,
                    field='row',
                    message=str(e),
                    value=None
                ))

        return ParseResult(
            total_rows=len(rows),
            valid_rows=len(parsed_trends),
            error_count=len(errors),
            warning_count=0,
            errors=errors,
            warnings=[],
            parsed_trends=parsed_trends,
            unmatched_points=list(unmatched_points),
        )

    def _parse_alarm_row(
        self,
        row: Dict[str, str],
        mappings: Dict[str, ColumnMapping],
        date_format: str,
        row_num: int,
    ) -> Optional[ParsedAlarm]:
        """Parse a single alarm row."""

        # Get timestamp (required)
        ts_mapping = mappings.get('timestamp')
        if not ts_mapping:
            raise ValueError("No timestamp mapping configured")

        ts_value = row.get(ts_mapping.source_column, '').strip()
        if not ts_value:
            return None

        occurred_at = self._parse_datetime(ts_value, date_format)
        if not occurred_at:
            raise ValueError(f"Cannot parse timestamp: {ts_value}")

        # Get point ID (required)
        point_mapping = mappings.get('point_id')
        if not point_mapping:
            raise ValueError("No point_id mapping configured")

        point_id = row.get(point_mapping.source_column, '').strip()
        if not point_id:
            return None

        # Optional fields
        alarm_code = self._get_mapped_value(row, mappings, 'alarm_code')
        description = self._get_mapped_value(row, mappings, 'description')
        value = self._parse_float(self._get_mapped_value(row, mappings, 'value'))
        threshold = self._parse_float(self._get_mapped_value(row, mappings, 'threshold'))
        severity_raw = self._get_mapped_value(row, mappings, 'severity')
        state_raw = self._get_mapped_value(row, mappings, 'state')
        ack_by = self._get_mapped_value(row, mappings, 'acknowledged_by')
        notes = self._get_mapped_value(row, mappings, 'notes')

        # Normalize severity
        severity = self._normalize_severity(severity_raw) if severity_raw else None

        # Normalize state
        state = self._normalize_state(state_raw) if state_raw else None

        return ParsedAlarm(
            occurred_at=occurred_at,
            point_id=point_id,
            alarm_code=alarm_code,
            description=description,
            value=value,
            threshold=threshold,
            severity=severity,
            state=state,
            acknowledged_by=ack_by,
            notes=notes,
            raw_data=dict(row),
        )

    def _parse_trend_row(
        self,
        row: Dict[str, str],
        mappings: Dict[str, ColumnMapping],
        date_format: str,
        row_num: int,
    ) -> Optional[ParsedTrend]:
        """Parse a single trend row."""

        ts_mapping = mappings.get('timestamp')
        if not ts_mapping:
            raise ValueError("No timestamp mapping configured")

        ts_value = row.get(ts_mapping.source_column, '').strip()
        if not ts_value:
            return None

        recorded_at = self._parse_datetime(ts_value, date_format)
        if not recorded_at:
            raise ValueError(f"Cannot parse timestamp: {ts_value}")

        point_mapping = mappings.get('point_id')
        if not point_mapping:
            raise ValueError("No point_id mapping configured")

        point_id = row.get(point_mapping.source_column, '').strip()
        if not point_id:
            return None

        value_str = self._get_mapped_value(row, mappings, 'value')
        value = self._parse_float(value_str)
        if value is None:
            return None

        unit = self._get_mapped_value(row, mappings, 'unit')
        quality = self._get_mapped_value(row, mappings, 'quality') or 'good'

        return ParsedTrend(
            recorded_at=recorded_at,
            point_id=point_id,
            value=value,
            unit=unit,
            quality=quality.lower() if quality in ['Good', 'Bad', 'Uncertain'] else 'good',
        )

    def _get_mapped_value(
        self,
        row: Dict[str, str],
        mappings: Dict[str, ColumnMapping],
        field: str,
    ) -> Optional[str]:
        """Get value from row using mapping."""
        mapping = mappings.get(field)
        if not mapping:
            return None
        value = row.get(mapping.source_column, '').strip()
        return value if value else None

    def _detect_file_format(self, content: str, filename: str) -> FileFormat:
        """Detect file format from extension or content."""
        ext = Path(filename).suffix.lower() if filename else ''

        if ext in ['.json']:
            return FileFormat.JSON
        if ext in ['.xlsx', '.xls']:
            return FileFormat.EXCEL
        if ext in ['.xml']:
            return FileFormat.XML

        # Check content
        content_start = content[:100].strip()
        if content_start.startswith('{') or content_start.startswith('['):
            return FileFormat.JSON
        if content_start.startswith('<?xml'):
            return FileFormat.XML

        return FileFormat.CSV

    def _detect_json_format(self, content: str) -> FormatDetectionResult:
        """Detect format from JSON content."""
        try:
            data = json.loads(content)

            if isinstance(data, list) and len(data) > 0:
                columns = list(data[0].keys())
                row_count = len(data)
                sample_rows = data[:10]
            elif isinstance(data, dict):
                columns = list(data.keys())
                row_count = 1
                sample_rows = [data]
            else:
                raise ValueError("Unsupported JSON structure")

            return FormatDetectionResult(
                file_format=FileFormat.JSON,
                delimiter='',
                date_format='YYYY-MM-DD HH:MI:SS',
                columns=columns,
                row_count=row_count,
                sample_rows=sample_rows,
                suggested_mappings=self._suggest_mappings(columns),
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")

    def _detect_delimiter(self, content: str) -> str:
        """Detect CSV delimiter."""
        first_line = content.split('\n')[0]

        # Count occurrences
        comma_count = first_line.count(',')
        semicolon_count = first_line.count(';')
        tab_count = first_line.count('\t')

        if semicolon_count > comma_count and semicolon_count > tab_count:
            return ';'
        if tab_count > comma_count:
            return '\t'
        return ','

    def _detect_date_format(
        self,
        date_values: List[str]
    ) -> Tuple[str, Optional[datetime], Optional[datetime]]:
        """Detect date format from sample values."""

        for fmt in self.DATE_FORMATS:
            matches = 0
            parsed_dates = []

            for val in date_values:
                if not val:
                    continue
                try:
                    dt = datetime.strptime(val.strip(), fmt)
                    matches += 1
                    parsed_dates.append(dt)
                except ValueError:
                    pass

            if matches > len(date_values) * 0.8:  # 80% match threshold
                # Convert to our format string
                format_str = fmt.replace('%Y', 'YYYY').replace('%m', 'MM').replace('%d', 'DD')
                format_str = format_str.replace('%H', 'HH').replace('%M', 'MI').replace('%S', 'SS')
                format_str = format_str.replace('%I', 'HH').replace('%p', 'AM')

                date_start = min(parsed_dates) if parsed_dates else None
                date_end = max(parsed_dates) if parsed_dates else None

                return format_str, date_start, date_end

        return 'YYYY-MM-DD HH:MI:SS', None, None

    def _detect_vendor(self, point_ids: List[str]) -> Optional[str]:
        """Detect BMS vendor from point ID patterns."""
        combined = ' '.join(point_ids)

        for vendor, patterns in self.VENDOR_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, combined, re.IGNORECASE):
                    return vendor

        return None

    def _find_column(self, columns: List[str], patterns: List[str]) -> Optional[str]:
        """Find column matching any of the patterns."""
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in patterns:
                return col
        return None

    def _suggest_mappings(self, columns: List[str]) -> Dict[str, str]:
        """Suggest SENTINEL field mappings for columns."""
        mappings = {}

        patterns = [
            ('timestamp', self.TIMESTAMP_PATTERNS),
            ('point_id', self.POINT_ID_PATTERNS),
            ('alarm_code', self.ALARM_CODE_PATTERNS),
            ('description', self.DESCRIPTION_PATTERNS),
            ('value', self.VALUE_PATTERNS),
            ('threshold', self.THRESHOLD_PATTERNS),
            ('severity', self.SEVERITY_PATTERNS),
            ('state', self.STATE_PATTERNS),
            ('acknowledged_by', self.ACK_BY_PATTERNS),
            ('notes', self.NOTES_PATTERNS),
        ]

        for sentinel_field, field_patterns in patterns:
            match = self._find_column(columns, field_patterns)
            if match:
                mappings[sentinel_field] = match

        return mappings

    def _parse_datetime(self, value: str, format_hint: str) -> Optional[datetime]:
        """Parse datetime from string."""
        if not value:
            return None

        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue

        return None

    def _parse_float(self, value: Optional[str]) -> Optional[float]:
        """Parse float from string."""
        if not value:
            return None
        try:
            return float(value.replace(',', '.'))
        except (ValueError, TypeError):
            return None

    def _normalize_severity(self, value: str) -> Optional[Severity]:
        """Normalize severity value."""
        if not value:
            return None

        v = value.upper().strip()

        if v in ['1', 'CRITICAL', 'URGENT', 'EMERGENCY', 'LIFE_SAFETY']:
            return Severity.CRITICAL
        if v in ['2', 'HIGH', 'MAJOR', 'IMPORTANT']:
            return Severity.HIGH
        if v in ['3', 'MEDIUM', 'MODERATE', 'NORMAL', 'MINOR']:
            return Severity.MEDIUM
        if v in ['4', 'LOW', 'INFO', 'ADVISORY', 'STATUS']:
            return Severity.LOW

        return None

    def _normalize_state(self, value: str) -> Optional[AlarmState]:
        """Normalize alarm state value."""
        if not value:
            return None

        v = value.upper().strip()

        if v in ['ACTIVE', 'ON', 'ALARM', 'TRIGGERED', 'RAISED']:
            return AlarmState.ACTIVE
        if v in ['ACKNOWLEDGED', 'ACK', 'ACKED']:
            return AlarmState.ACKNOWLEDGED
        if v in ['CLEARED', 'CLEAR', 'OFF', 'NORMAL', 'RESOLVED', 'RETURNED']:
            return AlarmState.CLEARED

        return None

    @staticmethod
    def compute_hash(alarm: ParsedAlarm) -> str:
        """Compute deduplication hash for alarm."""
        key = f"{alarm.occurred_at.isoformat()}|{alarm.point_id}|{alarm.alarm_code or ''}"
        return hashlib.md5(key.encode()).hexdigest()
