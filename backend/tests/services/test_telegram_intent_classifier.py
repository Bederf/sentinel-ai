"""Tests for Telegram Intent Classifier."""

from app.services.telegram_intent_classifier import (
    TelegramIntent,
    classify_intent,
)


class TestClassifyIntent:
    # --- Rule 1: callback + active session -> CHECKLIST_REPLY ---
    def test_callback_with_active_session(self):
        intent, _conf = classify_intent("", True, callback_data="inspect:filter:good")
        assert intent == TelegramIntent.CHECKLIST_REPLY
        assert _conf == 1.0

    def test_callback_with_session_ignores_text(self):
        intent, _conf = classify_intent("some text", True, callback_data="inspect:filter:good")
        assert intent == TelegramIntent.CHECKLIST_REPLY

    # --- Rule 2: callback without session -> parse flow ---
    def test_callback_menu_start_complaint(self):
        intent, _conf = classify_intent("", False, callback_data="menu:start:complaint")
        assert intent == TelegramIntent.CLIENT_COMPLAINT
        assert _conf == 0.95

    def test_callback_menu_start_inspection(self):
        intent, _conf = classify_intent("", False, callback_data="menu:start:inspection")
        assert intent == TelegramIntent.TECHNICIAN_REPORT

    def test_callback_menu_start_wo_check(self):
        intent, _conf = classify_intent("", False, callback_data="menu:start:wo_check")
        assert intent == TelegramIntent.WO_UPDATE

    def test_callback_complaint_category(self):
        intent, _conf = classify_intent("", False, callback_data="complaint:category:hvac")
        assert intent == TelegramIntent.CLIENT_COMPLAINT

    def test_callback_unknown_prefix(self):
        intent, _conf = classify_intent("", False, callback_data="xyz:foo:bar")
        assert intent == TelegramIntent.UNKNOWN

    # --- Rule 3: active session + free text -> CHECKLIST_REPLY ---
    def test_active_session_free_text(self):
        intent, _conf = classify_intent("Level 3, near the kitchen", True)
        assert intent == TelegramIntent.CHECKLIST_REPLY
        assert _conf == 0.9

    # --- Rule 4: WO pattern ---
    def test_wo_pattern_with_done(self):
        intent, _conf = classify_intent("WO-2026-0045 done", False)
        assert intent == TelegramIntent.WO_UPDATE
        assert _conf == 0.95

    def test_wo_pattern_only(self):
        intent, _conf = classify_intent("Check WO-2026-0045", False)
        assert intent == TelegramIntent.WO_UPDATE
        assert _conf == 0.85

    def test_wo_completed(self):
        intent, _conf = classify_intent("WO-2026-1234 completed", False)
        assert intent == TelegramIntent.WO_UPDATE
        assert _conf == 0.95

    # --- Rule 5: Equipment ID ---
    def test_equipment_id_sxxx(self):
        intent, _conf = classify_intent("I'm at S002-AHU-L2-001 starting inspection", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT
        assert _conf == 0.85

    def test_equipment_ahu(self):
        intent, _conf = classify_intent("AHU on level 2 making noise", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT

    def test_equipment_fcu(self):
        intent, _conf = classify_intent("FCU not cooling properly", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT

    # --- Rule 6: Technical vocab ---
    def test_tech_vocab_inspection(self):
        intent, _conf = classify_intent("starting inspection of the unit", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT
        assert _conf >= 0.75

    def test_tech_vocab_vibration(self):
        intent, _conf = classify_intent("noticed excessive vibration on the motor", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT

    def test_tech_vocab_pressure_drop(self):
        intent, _conf = classify_intent("pressure drop is very high", False)
        assert intent == TelegramIntent.TECHNICIAN_REPORT

    # --- Rule 7: Issue classifier (client complaint) ---
    def test_too_hot_client_complaint(self):
        intent, _conf = classify_intent("it's too hot on level 3", False)
        assert intent == TelegramIntent.CLIENT_COMPLAINT
        assert _conf >= 0.7

    def test_no_hot_water(self):
        intent, _conf = classify_intent("there's no hot water in the kitchen", False)
        assert intent == TelegramIntent.CLIENT_COMPLAINT

    def test_flooding(self):
        intent, _conf = classify_intent("flooding in the basement", False)
        assert intent == TelegramIntent.CLIENT_COMPLAINT

    # --- Rule 8: Ad-hoc fault ---
    def test_broken_chair(self):
        intent, _conf = classify_intent("broken chair desk 302", False)
        assert intent in (TelegramIntent.AD_HOC_FAULT, TelegramIntent.CLIENT_COMPLAINT)
        assert _conf >= 0.7

    def test_door_issue(self):
        intent, _conf = classify_intent("the door won't close properly", False)
        assert intent in (TelegramIntent.CLIENT_COMPLAINT, TelegramIntent.AD_HOC_FAULT)

    # --- Rule 9: Unknown ---
    def test_empty_message(self):
        intent, _conf = classify_intent("", False)
        assert intent == TelegramIntent.UNKNOWN
        assert _conf == 0.0

    def test_greeting(self):
        intent, _conf = classify_intent("hello", False)
        assert intent == TelegramIntent.UNKNOWN

    def test_random_text(self):
        intent, _conf = classify_intent("what's for lunch today?", False)
        assert intent == TelegramIntent.UNKNOWN


class TestEdgeCases:
    def test_none_text(self):
        intent, _conf = classify_intent(None, False)
        assert intent == TelegramIntent.UNKNOWN

    def test_whitespace_only(self):
        intent, _conf = classify_intent("   ", False)
        assert intent == TelegramIntent.UNKNOWN

    def test_callback_with_empty_text_no_session(self):
        intent, _conf = classify_intent("", False, callback_data="wo:status:completed")
        assert intent == TelegramIntent.WO_UPDATE
