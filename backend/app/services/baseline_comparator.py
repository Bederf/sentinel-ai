"""
Baseline Comparison Service (Phase 41-03)

Compare current sensor readings against equipment baseline.
Detects deviations and trends over time for predictive maintenance.

Workflow:
1. ONBOARDING: Capture baseline during condition inspection
2. SERVICE VISITS: Compare readings to baseline
3. PERIODIC MONITORING: Track trend direction

Thresholds are relative to baseline, not absolute values.
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class BaselineComparator:
    """Compare sensor readings against equipment baseline."""

    # Deviation thresholds (percentage change from baseline)
    THRESHOLDS = {
        'rms_vibration': {'warning': 30, 'critical': 100},
        'dominant_frequency_shift': {'warning': 5, 'critical': 10},
        'new_peaks': {'warning': 1, 'critical': 3},  # Count of new peaks
        'broadband_noise': {'warning': 20, 'critical': 50},
    }

    # Trend detection thresholds
    TREND_THRESHOLDS = {
        'stable': 10,      # <= 10% change considered stable
        'increasing': 25,  # > 25% increase is concerning
        'rapid_increase': 50  # > 50% is rapid degradation
    }

    def compare_to_baseline(
        self,
        current: Dict[str, Any],
        baseline: Dict[str, Any],
        measurement_type: str = "vibration"
    ) -> Dict[str, Any]:
        """
        Compare current reading to baseline.

        Args:
            current: Current sensor reading
            baseline: Baseline reading from onboarding/last service
            measurement_type: "vibration" or "audio"

        Returns:
            Comparison result with deviations and alerts
        """
        comparison = {
            'baseline_date': baseline.get('captured_at'),
            'baseline_condition': baseline.get('condition_at_capture'),
            'deviations': [],
            'alerts': [],
            'overall_status': 'normal',
            'trend_direction': 'stable'
        }

        if measurement_type == 'vibration':
            comparison.update(self._compare_vibration(current, baseline))
        elif measurement_type == 'audio':
            comparison.update(self._compare_audio(current, baseline))

        # Determine overall status
        if any(a['severity'] == 'critical' for a in comparison['alerts']):
            comparison['overall_status'] = 'critical'
        elif any(a['severity'] == 'warning' for a in comparison['alerts']):
            comparison['overall_status'] = 'warning'

        return comparison

    def _compare_vibration(self, current: Dict, baseline: Dict) -> Dict:
        """Compare vibration readings."""
        result = {'deviations': [], 'alerts': []}

        # RMS comparison
        current_rms = current.get('rms_total_ms2') or current.get('rms_value')
        baseline_rms = baseline.get('vibration_rms_ms2')

        if current_rms is not None and baseline_rms is not None and baseline_rms > 0:
            change_pct = ((current_rms - baseline_rms) / baseline_rms) * 100
            result['deviations'].append({
                'metric': 'rms_vibration',
                'baseline': baseline_rms,
                'current': current_rms,
                'change_pct': round(change_pct, 1)
            })

            if change_pct > self.THRESHOLDS['rms_vibration']['critical']:
                result['alerts'].append({
                    'severity': 'critical',
                    'metric': 'rms_vibration',
                    'message': f'Vibration {change_pct:+.0f}% from baseline - critical degradation'
                })
            elif change_pct > self.THRESHOLDS['rms_vibration']['warning']:
                result['alerts'].append({
                    'severity': 'warning',
                    'metric': 'rms_vibration',
                    'message': f'Vibration {change_pct:+.0f}% from baseline - monitor closely'
                })

        # Dominant frequency comparison
        current_dom = current.get('dominant_frequency_hz')
        baseline_dom = baseline.get('dominant_frequency_hz')

        if current_dom is not None and baseline_dom is not None and baseline_dom > 0:
            freq_shift_pct = abs((current_dom - baseline_dom) / baseline_dom) * 100
            result['deviations'].append({
                'metric': 'dominant_frequency',
                'baseline_hz': baseline_dom,
                'current_hz': current_dom,
                'shift_pct': round(freq_shift_pct, 1)
            })

            if freq_shift_pct > self.THRESHOLDS['dominant_frequency_shift']['critical']:
                result['alerts'].append({
                    'severity': 'critical',
                    'metric': 'dominant_frequency',
                    'message': f'Dominant frequency shifted {freq_shift_pct:.0f}% - investigate'
                })
            elif freq_shift_pct > self.THRESHOLDS['dominant_frequency_shift']['warning']:
                result['alerts'].append({
                    'severity': 'warning',
                    'metric': 'dominant_frequency',
                    'message': f'Dominant frequency shifted {freq_shift_pct:.0f}%'
                })

        # Frequency peak comparison - detect new peaks
        current_peaks = set(current.get('peak_frequencies_hz', []))
        baseline_peaks_list = baseline.get('vibration_peak_frequencies_hz', [])

        if isinstance(baseline_peaks_list, list):
            baseline_peaks = set(baseline_peaks_list)
        else:
            baseline_peaks = set()

        # New peaks (not in baseline, with 5% tolerance)
        new_peaks = []
        for cp in current_peaks:
            is_new = True
            for bp in baseline_peaks:
                if bp > 0 and abs(cp - bp) / bp < 0.05:  # Within 5%
                    is_new = False
                    break
            if is_new:
                new_peaks.append(cp)

        if new_peaks:
            result['deviations'].append({
                'metric': 'new_frequency_peaks',
                'new_peaks_hz': new_peaks,
                'count': len(new_peaks)
            })

            if len(new_peaks) >= self.THRESHOLDS['new_peaks']['critical']:
                result['alerts'].append({
                    'severity': 'critical',
                    'metric': 'new_peaks',
                    'message': f'{len(new_peaks)} new frequency peaks detected - investigate'
                })
            elif len(new_peaks) >= self.THRESHOLDS['new_peaks']['warning']:
                result['alerts'].append({
                    'severity': 'warning',
                    'metric': 'new_peaks',
                    'message': f'New frequency peak at {new_peaks[0]:.1f} Hz'
                })

        return result

    def _compare_audio(self, current: Dict, baseline: Dict) -> Dict:
        """Compare audio readings."""
        result = {'deviations': [], 'alerts': []}

        # Noise floor comparison
        current_noise = current.get('overall_level_db')
        baseline_noise = baseline.get('audio_noise_floor_db')

        if current_noise is not None and baseline_noise is not None:
            change_db = current_noise - baseline_noise
            result['deviations'].append({
                'metric': 'noise_level',
                'baseline_db': baseline_noise,
                'current_db': current_noise,
                'change_db': round(change_db, 1)
            })

            if change_db > 6:  # 6dB = ~2x louder
                result['alerts'].append({
                    'severity': 'warning',
                    'metric': 'noise_level',
                    'message': f'Noise level +{change_db:.0f}dB from baseline'
                })
            if change_db > 12:  # 12dB = ~4x louder
                result['alerts'].append({
                    'severity': 'critical',
                    'metric': 'noise_level',
                    'message': f'Noise level +{change_db:.0f}dB from baseline - significant increase'
                })

        # Dominant frequency comparison
        current_dom = current.get('dominant_frequency_hz')
        baseline_dom = baseline.get('audio_dominant_frequency_hz')

        if current_dom is not None and baseline_dom is not None and baseline_dom > 0:
            freq_shift_pct = abs((current_dom - baseline_dom) / baseline_dom) * 100
            if freq_shift_pct > 10:  # More than 10% shift
                result['deviations'].append({
                    'metric': 'audio_dominant_frequency',
                    'baseline_hz': baseline_dom,
                    'current_hz': current_dom,
                    'shift_pct': round(freq_shift_pct, 1)
                })
                result['alerts'].append({
                    'severity': 'warning',
                    'metric': 'audio_frequency',
                    'message': f'Audio dominant frequency shifted {freq_shift_pct:.0f}%'
                })

        return result

    def generate_trend_report(
        self,
        equipment_id: str,
        recordings: List[Dict],
        baseline: Dict
    ) -> Dict[str, Any]:
        """
        Generate trend analysis from multiple readings.

        Args:
            equipment_id: Equipment identifier
            recordings: List of historical readings
            baseline: Baseline reading

        Returns:
            Trend analysis with direction and prediction
        """
        if len(recordings) < 2:
            return {
                'trend': 'insufficient_data',
                'message': 'Need 2+ readings for trend',
                'readings_count': len(recordings)
            }

        # Sort by date
        sorted_recs = sorted(recordings, key=lambda r: r.get('created_at', ''))

        # Calculate trend (simple linear regression on RMS)
        rms_values = [r.get('rms_total_ms2') or r.get('rms_value') for r in sorted_recs]
        rms_values = [v for v in rms_values if v is not None]

        if len(rms_values) >= 2:
            # Simple trend: first vs last
            first_rms = rms_values[0]
            last_rms = rms_values[-1]

            if first_rms > 0:
                change_pct = ((last_rms - first_rms) / first_rms) * 100
            else:
                change_pct = 0

            # Determine trend direction
            if change_pct > self.TREND_THRESHOLDS['rapid_increase']:
                trend = 'rapid_increase'
                trend_emoji = '📈🔴'
            elif change_pct > self.TREND_THRESHOLDS['increasing']:
                trend = 'increasing'
                trend_emoji = '📈⚠️'
            elif change_pct > self.TREND_THRESHOLDS['stable']:
                trend = 'slight_increase'
                trend_emoji = '📈'
            elif change_pct < -self.TREND_THRESHOLDS['stable']:
                trend = 'decreasing'
                trend_emoji = '📉'
            else:
                trend = 'stable'
                trend_emoji = '➡️'

            # Calculate rate of change
            first_date = sorted_recs[0].get('created_at')
            last_date = sorted_recs[-1].get('created_at')

            return {
                'trend': trend,
                'trend_emoji': trend_emoji,
                'change_pct': round(change_pct, 1),
                'readings_count': len(recordings),
                'first_reading': first_date,
                'last_reading': last_date,
                'first_rms': first_rms,
                'last_rms': last_rms,
                'message': f'Vibration {"rising" if change_pct > 0 else "falling"} {abs(change_pct):.0f}% over {len(recordings)} readings',
                'action_required': trend in ('rapid_increase', 'increasing')
            }

        return {
            'trend': 'stable',
            'message': 'Insufficient RMS data for trend'
        }

    def calculate_deviation_score(
        self,
        comparison: Dict[str, Any]
    ) -> int:
        """
        Calculate a 0-100 score based on deviation from baseline.

        Args:
            comparison: Result from compare_to_baseline()

        Returns:
            Score where 100 = matches baseline, 0 = critical deviation
        """
        base_score = 100

        for deviation in comparison.get('deviations', []):
            metric = deviation.get('metric', '')

            if 'change_pct' in deviation:
                change = abs(deviation['change_pct'])
                if metric == 'rms_vibration':
                    # RMS change: -1 point per 2% deviation
                    base_score -= min(50, change / 2)
                elif metric == 'dominant_frequency':
                    # Frequency shift: -5 points per 1% shift
                    base_score -= min(30, change * 5)
            elif metric == 'new_frequency_peaks':
                # New peaks: -10 points each
                count = deviation.get('count', 0)
                base_score -= min(30, count * 10)

        return max(0, min(100, round(base_score)))


# Singleton instance
_comparator_instance: Optional[BaselineComparator] = None


def get_baseline_comparator() -> BaselineComparator:
    """Get or create the singleton comparator instance."""
    global _comparator_instance
    if _comparator_instance is None:
        _comparator_instance = BaselineComparator()
    return _comparator_instance
