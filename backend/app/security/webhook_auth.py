"""
Webhook Authentication and Rate Limiting.

Verifies incoming webhook requests from external systems:
    - Signature verification (HMAC-SHA256)
    - Sender allowlisting
    - Rate limiting (per sender, per endpoint)
    - Payload size enforcement (MAX_WEBHOOK_BODY_SIZE)
    - Prompt injection scanning for webhook content

Applies to email intake (n8n), WhatsApp webhooks, and
any future external integrations.
"""
