from datetime import datetime, timedelta, timezone

from app.services.fault_episode_builder import build_fault_episodes, detect_cycling_signals


BASE = datetime(2026, 6, 17, 8, 0, tzinfo=timezone.utc)


def event(
    minutes: int,
    equipment_code: str = "S002-AHU-B1-001",
    to_state: str = "HIGH_LIMIT",
    from_state: str = "NORMAL",
) -> dict:
    return {
        "id": f"{equipment_code}-{minutes}-{to_state}",
        "equipment_code": equipment_code,
        "alarm_code": "OUT_OF_RANGE",
        "recorded_at": BASE + timedelta(minutes=minutes),
        "message_text": f"{equipment_code} {to_state}",
        "raw_payload": {
            "to_state": to_state,
            "from_state": from_state,
        },
    }


def test_normal_transition_closes_episode():
    episodes = build_fault_episodes(
        [
            event(0, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(12, to_state="NORMAL", from_state="HIGH_LIMIT"),
        ]
    )

    assert len(episodes) == 1
    assert episodes[0].status == "closed"
    assert episodes[0].started_at == BASE
    assert episodes[0].ended_at == BASE + timedelta(minutes=12)


def test_never_resolving_fault_remains_open():
    episodes = build_fault_episodes(
        [
            event(0, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(40, to_state="HIGH_LIMIT", from_state="NORMAL"),
        ]
    )

    assert len(episodes) == 1
    assert episodes[0].status == "open"
    assert episodes[0].ended_at is None
    assert episodes[0].event_count == 2


def test_simultaneous_multi_equipment_faults_are_separate_episodes():
    episodes = build_fault_episodes(
        [
            event(0, equipment_code="S002-AHU-B1-001"),
            event(0, equipment_code="S002-CT-B1-001"),
            event(0, equipment_code="S002-CHILLER-B1-001"),
            event(10, equipment_code="S002-AHU-B1-001", to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(10, equipment_code="S002-CT-B1-001", to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(10, equipment_code="S002-CHILLER-B1-001", to_state="NORMAL", from_state="HIGH_LIMIT"),
        ]
    )

    assert len(episodes) == 3
    assert {episode.equipment_code for episode in episodes} == {
        "S002-AHU-B1-001",
        "S002-CT-B1-001",
        "S002-CHILLER-B1-001",
    }
    assert all(episode.status == "closed" for episode in episodes)


def test_irregular_intervals_and_missed_poll_gaps_still_close_on_normal():
    episodes = build_fault_episodes(
        [
            event(0, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(7, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(54, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(143, to_state="NORMAL", from_state="HIGH_LIMIT"),
        ]
    )

    assert len(episodes) == 1
    assert episodes[0].status == "closed"
    assert episodes[0].ended_at == BASE + timedelta(minutes=143)


def test_rapid_refault_after_closure_opens_new_episode():
    episodes = build_fault_episodes(
        [
            event(0, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(5, to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(6, to_state="HIGH_LIMIT", from_state="NORMAL"),
            event(9, to_state="NORMAL", from_state="HIGH_LIMIT"),
        ]
    )

    assert len(episodes) == 2
    assert [episode.status for episode in episodes] == ["closed", "closed"]
    assert episodes[0].started_at == BASE
    assert episodes[0].ended_at == BASE + timedelta(minutes=5)
    assert episodes[1].started_at == BASE + timedelta(minutes=6)
    assert episodes[1].ended_at == BASE + timedelta(minutes=9)


def test_repeated_closed_episodes_emit_cycling_signal():
    episodes = build_fault_episodes(
        [
            event(0),
            event(5, to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(15),
            event(20, to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(30),
            event(35, to_state="NORMAL", from_state="HIGH_LIMIT"),
            event(45),
            event(50, to_state="NORMAL", from_state="HIGH_LIMIT"),
        ]
    )

    signals = detect_cycling_signals(episodes, min_closed_cycles=3, max_median_period_minutes=60)

    assert len(signals) == 1
    assert signals[0].equipment_code == "S002-AHU-B1-001"
    assert signals[0].cycle_count == 4
    assert signals[0].median_period_minutes == 15.0
    assert signals[0].classification == "equipment_hunting_or_short_cycling"


def test_unresolved_fault_does_not_emit_cycling_signal():
    episodes = build_fault_episodes(
        [
            event(0),
            event(15),
            event(30),
        ]
    )

    signals = detect_cycling_signals(episodes, min_closed_cycles=3, max_median_period_minutes=60)

    assert signals == []
