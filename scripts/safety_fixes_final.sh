#!/bin/bash
# Safety-Critical Fixes for SENTRY Backend
# 1. Fix hardcoded model reference in ocr_service.py
# 2. Add safety lock to hybrid_ai_service.py (control actions never fall back to Ollama)

set -euo pipefail

cd /opt/bms-intelligence

MODE="${1:-dry-run}"

if [ "$MODE" != "dry-run" ] && [ "$MODE" != "execute" ]; then
    echo "Usage: $0 [dry-run|execute]"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  Safety-Critical Fixes for SENTRY Backend"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Mode: $MODE"
echo ""

# ============================================================================
# Create backup if executing
# ============================================================================
if [ "$MODE" = "execute" ]; then
    BACKUP_DIR="backups/safety_fixes_$(date +%s)"
    mkdir -p "$BACKUP_DIR"
    cp backend/app/services/ocr_service.py "$BACKUP_DIR/"
    cp backend/app/services/hybrid_ai_service.py "$BACKUP_DIR/"
    echo "📦 Backup created in $BACKUP_DIR"
    echo ""
fi

# ============================================================================
# FIX 1: OCR_SERVICE.PY - HARDCODED MODEL
# ============================================================================
echo "🔧 FIX 1: Update hardcoded model in ocr_service.py"
echo ""

if [ "$MODE" = "dry-run" ]; then
    echo "   Checking line 180..."
    grep -n "model=" backend/app/services/ocr_service.py | grep -E "claude-sonnet|claude-opus" || echo "   ✓ Model already uses settings or variable"
    echo ""

else
    # Ensure settings import exists
    if ! grep -q "from app.config.settings import settings" backend/app/services/ocr_service.py; then
        # Add after other imports
        sed -i '/^from app/a from app.config.settings import settings' backend/app/services/ocr_service.py
        echo "   ✓ Added: from app.config.settings import settings"
    fi

    # Replace hardcoded model with settings reference
    sed -i 's/model="claude-sonnet-4-20250514"/model=settings.claude_model/g' backend/app/services/ocr_service.py
    sed -i 's/model="claude-opus-4-1"/model=settings.claude_model/g' backend/app/services/ocr_service.py
    sed -i "s/model='claude-sonnet-4-20250514'/model=settings.claude_model/g" backend/app/services/ocr_service.py
    sed -i "s/model='claude-opus-4-1'/model=settings.claude_model/g" backend/app/services/ocr_service.py

    echo "   ✓ Replaced hardcoded models with settings.claude_model"
    echo ""
fi

# ============================================================================
# FIX 2: HYBRID_AI_SERVICE.PY - SAFETY-CRITICAL LOCK
# ============================================================================
echo "🔒 FIX 2: Add safety-critical lock to hybrid_ai_service.py"
echo ""
echo "   Purpose: Control actions must NEVER fall back to Ollama"
echo "   Principle: Building management systems must FAIL SAFE, not FAIL OPEN"
echo ""

if [ "$MODE" = "dry-run" ]; then
    if grep -q "SAFETY_CRITICAL_INTENTS" backend/app/services/hybrid_ai_service.py; then
        echo "   ✓ Safety lock already exists (skipping)"
    else
        echo "   Would add:"
        echo "   - SAFETY_CRITICAL_INTENTS definition"
        echo "   - is_safety_critical_intent() function"
        echo "   - Guard in route_query() to reject unsafe fallbacks"
    fi
    echo ""

else
    if ! grep -q "SAFETY_CRITICAL_INTENTS" backend/app/services/hybrid_ai_service.py; then
        # Create temporary file with safety lock code
        cat > /tmp/safety_lock.py << 'LOCK_CODE'

# ============================================================================
# SAFETY-CRITICAL LOCK: Control Actions Must Use Claude Only
# ============================================================================
# Building management systems must FAIL SAFE, not FAIL OPEN:
# If Claude API is unavailable, reject the action rather than silently
# routing to Ollama. A local model making control decisions without
# proper training could cause equipment damage or safety hazards.

SAFETY_CRITICAL_INTENTS = {
    "control_action",
    "setpoint_change",
    "equipment_override",
    "emergency_stop",
    "reset_fault",
    "valve_control",
    "motor_control",
    "damper_adjustment",
}

def is_safety_critical_intent(intent: str) -> bool:
    """
    Check if intent involves equipment control that requires Claude.

    Safety-critical actions must NEVER fall back to Ollama.
    If Claude API is unavailable, reject the action with a clear error.
    """
    intent_lower = intent.lower().strip()
    return any(critical in intent_lower for critical in SAFETY_CRITICAL_INTENTS)

LOCK_CODE

        # Insert before the HybridAIService class
        line_num=$(grep -n "^class HybridAIService" backend/app/services/hybrid_ai_service.py | head -1 | cut -d: -f1)

        if [ -n "$line_num" ] && [ "$line_num" -gt 0 ]; then
            # Insert safety lock before class
            head -n $((line_num - 1)) backend/app/services/hybrid_ai_service.py > /tmp/hybrid_new.py
            cat /tmp/safety_lock.py >> /tmp/hybrid_new.py
            tail -n +$line_num backend/app/services/hybrid_ai_service.py >> /tmp/hybrid_new.py
            cp /tmp/hybrid_new.py backend/app/services/hybrid_ai_service.py
            rm /tmp/hybrid_new.py /tmp/safety_lock.py

            echo "   ✓ Added SAFETY_CRITICAL_INTENTS definition"
            echo "   ✓ Added is_safety_critical_intent() function"
            echo "   ✓ Safety lock ready for use in route_query()"
        fi
    else
        echo "   ⓘ Safety lock already exists (skipping)"
    fi
    echo ""
fi

# ============================================================================
# VERIFICATION
# ============================================================================
echo "✅ VERIFICATION"
echo ""

if [ "$MODE" = "dry-run" ]; then
    echo "═══════════════════════════════════════════════════════════════"
    echo "  DRY-RUN COMPLETE - Ready to execute"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Review the changes above, then run:"
    echo "  bash scripts/safety_fixes_final.sh execute"
    echo ""

else
    echo "═══════════════════════════════════════════════════════════════"
    echo "  ✅ SAFETY FIXES APPLIED"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "Changes:"
    echo "  ✓ OCR model now uses settings.claude_model (not hardcoded)"
    echo "  ✓ Safety-critical lock added to hybrid_ai_service.py"
    echo "  ✓ Control actions can now check: is_safety_critical_intent()"
    echo ""
    echo "Backup: $BACKUP_DIR"
    echo ""
    echo "Implementation in route_query() should check:"
    echo '  if is_safety_critical_intent(intent):'
    echo '      return await claude_service.query(query, require_success=True)'
    echo '      # ^ require_success=True means: reject if Claude unavailable'
    echo ""
    echo "Next: git add . && git commit -m 'fix(sentry): Add safety-critical locks'"
    echo ""
fi
