"""
Clawd AI Bridge Integration for Work Orders.

This script shows how to integrate with the existing clawd_ai_bridge.py

Add these patterns and handlers to $SENTRY_HOME/tools/clawd_ai_bridge.py
"""

# PATTERNS TO ADD TO clawd_ai_bridge.py:

"""
work_order_patterns = [
    r"(done|completed|finished).*work\s+order\s+(\w+)",
    r"work\s+order\s+(\w+).*\s(done|completed|finished)",
    r"sr-\d{4}-\w+",  # Service record code pattern
    r"service\s+completed.*(\w+)",
]

def is_work_order_message(message: str) -> tuple[bool, str | None]:
    """Detect if message is work order completion.

    Returns:
        (is_wo: bool, service_record_code: str | None)
    """
    import re

    # Extract service record code
    sr_pattern = r'(sr-\d{4}-\w{6})'
    match = re.search(sr_pattern, message.lower())

    if match:
        return True, match.group(1).upper()

    # Check for "done" without code (might need context)
    done_patterns = [
        r'\bdone\b',
        r'\bcompleted\b',
        r'\bfinished\b'
    ]

    for pattern in done_patterns:
        if re.search(pattern, message.lower()):
            # This would need conversation context to get the SR code
            return True, None

    return False, None
"""

# HANDLERS TO ADD TO clawd_ai_bridge.py:

"""
from tools.wo_conversation_handler import WOConversationHandler

def handle_work_order_completion(service_record_code: str, telegram_user_id: str) -> str:
    """Handle technician's 'done' reply for work order.

    Args:
        service_record_code: Service record code (e.g., SR-2026-ABC123)
        telegram_user_id: Technician's Telegram user ID

    Returns:
        Response message to send to technician
    """
    try:
        handler = WOConversationHandler(service_record_code, telegram_user_id)

        # Get first prompt
        response = handler.handle_initial_done()

        if response:
            return response
        else:
            return "❌ Could not start data collection. Please check the service record code."

    except Exception as e:
        return f"❌ Error: {str(e)}"

def handle_wo_file_upload(
    service_record_code: str,
    telegram_user_id: str,
    file_info: dict,
    message_type: str
) -> str:
    """Handle file upload during data collection.

    Args:
        service_record_code: Service record code
        telegram_user_id: Technician's Telegram user ID
        file_info: File information dict
        message_type: Type of file (photo/audio/document)

    Returns:
        Response message with next prompt or completion
    """
    try:
        handler = WOConversationHandler(service_record_code, telegram_user_id)

        response = handler.handle_file_reply(file_info, message_type)

        if response:
            return response
        else:
            return "❌ Could not process file. Please try again."

    except Exception as e:
        return f"❌ Error: {str(e)}"

def handle_wo_status(service_record_code: str, telegram_user_id: str) -> str:
    """Show current data collection status.

    Args:
        service_record_code: Service record code
        telegram_user_id: Technician's Telegram user ID

    Returns:
        Formatted status message
    """
    try:
        handler = WOConversationHandler(service_record_code, telegram_user_id)
        return handler.format_status_message()

    except Exception as e:
        return f"❌ Error: {str(e)}"
"""

# INTEGRATION POINTS IN clawd_ai_bridge.py:

# Add to detect_and_route() function:
"""
# Check if this is a work order message
is_wo, sr_code = is_work_order_message(message)
if is_wo:
    # Get service record code from context if not in message
    if not sr_code:
        sr_code = get_conversation_context(user_id, "last_sr_code")

    if sr_code:
        return {
            "route": "work_order",
            "handler": "handle_work_order_completion",
            "params": [sr_code, user_id]
        }
"""

# Add to file upload handling:
"""
# Check if this is during WO data collection
if has_active_wo_collection(user_id):
    sr_code = get_conversation_context(user_id, "active_sr_code")
    return {
        "route": "work_order_file",
        "handler": "handle_wo_file_upload",
        "params": [sr_code, user_id, file_info, message_type]
    }
"""

# Add to message handling:
"""
# Check for status requests
if re.search(r'status|progress', message.lower()):
    sr_code = get_conversation_context(user_id, "active_sr_code")
    if sr_code:
        return {
            "route": "work_order_status",
            "handler": "handle_wo_status",
            "params": [sr_code, user_id]
        }
"""

# Add to route handlers:
"""
# Work order routes
if route == "work_order":
    return handle_work_order_completion(*params)
elif route == "work_order_file":
    return handle_wo_file_upload(*params)
elif route == "work_order_status":
    return handle_wo_status(*params)
"""
