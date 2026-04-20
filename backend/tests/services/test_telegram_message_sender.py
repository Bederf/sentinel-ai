"""Tests for TelegramMessageSender."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.telegram_message_sender import (
    ConfigurationError,
    InlineButton,
    InlineKeyboard,
    TelegramMessageSender,
    get_telegram_sender,
)


class TestInlineKeyboard:
    def test_to_telegram_format(self):
        kb = InlineKeyboard(
            rows=[
                [
                    InlineButton(label="Yes", callback_data="flow:action:yes"),
                    InlineButton(label="No", callback_data="flow:action:no"),
                ],
                [InlineButton(label="Skip", callback_data="flow:action:skip")],
            ]
        )
        result = kb.to_telegram()
        assert len(result["inline_keyboard"]) == 2
        assert result["inline_keyboard"][0][0]["text"] == "Yes"
        assert result["inline_keyboard"][0][0]["callback_data"] == "flow:action:yes"
        assert result["inline_keyboard"][1][0]["text"] == "Skip"

    def test_empty_keyboard(self):
        kb = InlineKeyboard()
        result = kb.to_telegram()
        assert result == {"inline_keyboard": []}


class TestTelegramMessageSender:
    @pytest.mark.asyncio
    async def test_send_text_without_keyboard(self):
        sender = TelegramMessageSender("test-token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 1}}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await sender.send_text("12345", "Hello")
            assert result["ok"] is True

            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]
            assert payload["chat_id"] == "12345"
            assert payload["text"] == "Hello"
            assert payload["parse_mode"] == "HTML"
            assert "reply_markup" not in payload

    @pytest.mark.asyncio
    async def test_send_text_with_keyboard(self):
        sender = TelegramMessageSender("test-token")
        kb = InlineKeyboard(rows=[[InlineButton(label="OK", callback_data="flow:ok:1")]])
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"message_id": 2}}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await sender.send_text("12345", "Pick one", keyboard=kb)
            payload = mock_client.post.call_args[1]["json"]
            assert "reply_markup" in payload
            assert payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "OK"

    @pytest.mark.asyncio
    async def test_send_text_calls_correct_url(self):
        sender = TelegramMessageSender("my-bot-token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await sender.send_text("123", "test")
            url = mock_client.post.call_args[0][0]
            assert url == "https://api.telegram.org/botmy-bot-token/sendMessage"

    @pytest.mark.asyncio
    async def test_answer_callback_query(self):
        sender = TelegramMessageSender("test-token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await sender.answer_callback_query("cbq-123", text="Done!")
            url = mock_client.post.call_args[0][0]
            assert "answerCallbackQuery" in url
            payload = mock_client.post.call_args[1]["json"]
            assert payload["callback_query_id"] == "cbq-123"
            assert payload["text"] == "Done!"

    @pytest.mark.asyncio
    async def test_edit_message_reply_markup_remove(self):
        sender = TelegramMessageSender("test-token")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True}

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_resp
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            await sender.edit_message_reply_markup("123", 456)
            payload = mock_client.post.call_args[1]["json"]
            assert payload["reply_markup"] == {"inline_keyboard": []}


class TestGetTelegramSender:
    def test_missing_token_raises_error(self):
        import app.services.telegram_message_sender as mod

        mod._sender_instance = None
        with patch.object(mod.settings, "telegram_bot_token", ""):
            with pytest.raises(ConfigurationError, match="telegram_bot_token"):
                get_telegram_sender()
        mod._sender_instance = None  # cleanup

    def test_valid_token_returns_sender(self):
        import app.services.telegram_message_sender as mod

        mod._sender_instance = None
        with patch.object(mod.settings, "telegram_bot_token", "valid-token"):
            sender = get_telegram_sender()
            assert isinstance(sender, TelegramMessageSender)
        mod._sender_instance = None
