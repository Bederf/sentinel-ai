SENTINEL-Branded Work Order Email Template
==========================================

Header:
- Logo: Sentinel SVG (inline)
- Banner: "SENTINEL BMS Intelligence"
- Color: #1a73e8 (Sentinel blue)

Body sections (same as plain text but with HTML formatting):
- WO reference box (highlighted)
- Equipment & Site info table
- Issue description
- Inspection checklist (if available)
- Field instructions
- Telegram commands section
- Footer with sentinel branding

Footer:
- "SENTINEL BMS Intelligence / Sentry"
- "This is an automated message from SENTINEL."

## Implementation Notes

The `_build_email_body` method returns plain text. The email is sent via `email_reply_service.send_reply(body_plain=body, body_html=None)`.

To add HTML rendering, `_send_email_notification` should generate an HTML version alongside the plain text and pass it as `body_html`. The HTML template should mirror all fields from `_build_email_body` with Sentinel branding applied.

Steps to implement:
1. Add `_build_email_body_html()` method — mirrors `_build_email_body` with HTML tags and Sentinel CSS
2. Modify `_send_email_notification` to call `_build_email_body_html()` and pass as `body_html`
3. Use `body_html` in `send_reply(to_email, subject, body_plain=plain, body_html=html)`

CSS variables for Sentinel brand:
--sentinel-blue: #1a73e8
--sentinel-dark: #202124
--sentinel-light: #f8f9fa
--sentinel-accent: #ea4335
