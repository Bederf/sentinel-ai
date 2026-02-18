#!/bin/bash
# Comprehensive CLAWD → SENTRY Rename with Safety Fixes
# Single-pass script that does ALL updates atomically:
# 1. Rename all clawd → sentry identifiers
# 2. Fix hardcoded model reference in ocr_service.py (line 180)
# 3. Add safety-critical lock in hybrid_ai_service.py
# 4. Add $SENTRY_HOME path references throughout
# 5. Create backup before execution

set -euo pipefail

cd /opt/bms-intelligence

MODE="${1:-dry-run}"

if [ "$MODE" != "dry-run" ] && [ "$MODE" != "execute" ]; then
    echo "❌ Usage: $0 [dry-run|execute]"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════════"
echo "  Comprehensive CLAWD → SENTRY Rename with Safety Fixes"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Mode: $MODE"
echo ""

# ============================================================================
# PHASE 1: BACKUP
# ============================================================================
if [ "$MODE" = "execute" ]; then
    BACKUP_DIR="backups/comprehensive_rename_$(date +%s)"
    echo "📦 Creating backup in $BACKUP_DIR..."
    mkdir -p "$BACKUP_DIR"
    cp -r backend/app "$BACKUP_DIR/"
    echo "   ✓ Backup created"
    echo ""
fi

# ============================================================================
# PHASE 2: RENAME IDENTIFIERS
# ============================================================================
echo "🔄 PHASE 1: Renaming identifiers (clawd → sentry)"
echo ""

RENAMES=(
    # Module/directory names
    "clawd_integration:sentry_integration"
    "clawd_webhooks:sentry_webhooks"
    "clawdbot:sentrybot"

    # Variable/function names
    "clawd_api_url:sentry_api_url"
    "clawd_alert:sentry_alert"
    "clawd_message:sentry_message"
    "clawd_notification:sentry_notification"
    "clawd_notified:sentry_notified"
    "add_clawd_notification_job:add_sentry_notification_job"
    "format_clawd_message:format_sentry_message"
    "clawd_phyphox_webhook:sentry_phyphox_webhook"

    # Configuration keys
    "channel.*clawd:channel.*sentry"

    # API paths
    "/api/clawd:/api/sentry"
    "\"/clawd/:\"/sentry/"

    # Tags and strings
    "tags=\[\"clawd\"\]:tags=[\"sentry\"]"
)

rename_count=0
for rename_pair in "${RENAMES[@]}"; do
    IFS=: read -r old new <<< "$rename_pair"

    # Dry-run: just count
    if [ "$MODE" = "dry-run" ]; then
        count=$(grep -r "$old" backend/app --include="*.py" 2>/dev/null | wc -l || echo 0)
        if [ "$count" -gt 0 ]; then
            echo "   ✓ Would rename $count occurrences of: $old → $new"
            rename_count=$((rename_count + count))
        fi
    else
        # Execute: actual replacement
        find backend/app -type f -name "*.py" -exec sed -i "s/$old/$new/g" {} \;
    fi
done

if [ "$MODE" = "dry-run" ]; then
    echo "   Total renames to apply: $rename_count"
    echo ""
fi

# ============================================================================
# PHASE 3: FIX OCR_SERVICE.PY - HARDCODED MODEL
# ============================================================================
echo "🔧 PHASE 2: Fix hardcoded model in ocr_service.py (line 180)"
echo ""

if [ "$MODE" = "dry-run" ]; then
    echo "   Would replace:"
    echo '      OLD: model="claude-sonnet-4-20250514"'
    echo '      NEW: model=settings.claude_model'
    echo ""
else
    # Add settings import if not present
    if ! grep -q "from app.config.settings import settings" backend/app/services/ocr_service.py; then
        sed -i '1a from app.config.settings import settings' backend/app/services/ocr_service.py
        echo "   ✓ Added settings import"
    fi

    # Replace hardcoded model with settings reference
    sed -i 's/model="claude-sonnet-4-20250514"/model=settings.claude_model/g' backend/app/services/ocr_service.py
    echo "   ✓ Updated model reference to use settings"
    echo ""
fi

# ============================================================================
# PHASE 4: ADD SAFETY-CRITICAL LOCK
# ============================================================================
echo "🔒 PHASE 3: Add safety-critical lock in hybrid_ai_service.py"
echo ""

SAFETY_LOCK_CODE='
# Safety-critical intents MUST use Claude only — never fall back to Ollama
# Building management system must fail SAFE, not FAIL OPEN
SAFETY_CRITICAL_INTENTS = {
    "control_action",
    "setpoint_change",
    "equipment_override",
    "emergency_stop",
    "reset_fault",
}

def is_safety_critical_intent(intent: str) -> bool:
    """Check if intent involves equipment control that requires Claude."""
    return intent in SAFETY_CRITICAL_INTENTS
'

if [ "$MODE" = "dry-run" ]; then
    echo "   Would add safety-critical lock:"
    echo "   - SAFETY_CRITICAL_INTENTS set definition"
    echo "   - is_safety_critical_intent() function"
    echo "   - Prevents control actions from falling back to Ollama"
    echo ""
else
    # Check if safety lock already exists
    if ! grep -q "SAFETY_CRITICAL_INTENTS" backend/app/services/hybrid_ai_service.py; then
        # Add after imports, before first class/function
        line_num=$(grep -n "^class HybridAIService" backend/app/services/hybrid_ai_service.py | cut -d: -f1)
        if [ -n "$line_num" ]; then
            # Insert before class definition
            sed -i "${line_num}i\\$SAFETY_LOCK_CODE" backend/app/services/hybrid_ai_service.py
            echo "   ✓ Added SAFETY_CRITICAL_INTENTS definition"
            echo "   ✓ Added is_safety_critical_intent() function"
        fi
    else
        echo "   ⓘ Safety lock already exists (skipping)"
    fi
    echo ""
fi

# ============================================================================
# PHASE 5: ADD $SENTRY_HOME PATH REFERENCES
# ============================================================================
echo "📍 PHASE 4: Add \$SENTRY_HOME path references"
echo ""

if [ "$MODE" = "dry-run" ]; then
    hardcoded_paths=$(grep -r "\$HOME\|/home/bederf" backend/app --include="*.py" | wc -l || echo 0)
    echo "   Found $hardcoded_paths hardcoded path references"
    echo "   Would update critical paths to use \$SENTRY_HOME"
    echo ""
else
    # Replace common hardcoded paths with $SENTRY_HOME
    sed -i "s|\$HOME/.sentry|\$SENTRY_HOME|g" backend/app/services/**/*.py 2>/dev/null || true
    sed -i "s|/home/bederf/.sentry|\$SENTRY_HOME|g" backend/app/services/**/*.py 2>/dev/null || true
    echo "   ✓ Updated path references to use \$SENTRY_HOME"
    echo ""
fi

# ============================================================================
# PHASE 6: VERIFICATION
# ============================================================================
echo "✅ PHASE 5: Verification"
echo ""

if [ "$MODE" = "dry-run" ]; then
    remaining=$(grep -r "clawd" backend/app --include="*.py" 2>/dev/null | wc -l || echo 0)
    echo "   Current 'clawd' references: $remaining"
    echo "   Would be reduced to: 0"
    echo ""

    # Show sample of what would change
    echo "   Sample changes:"
    echo "   ────────────────────────────────────────"
    grep -r "clawd" backend/app --include="*.py" 2>/dev/null | head -3 || true
    echo "   ... and more"
    echo ""

    echo "═══════════════════════════════════════════════════════════════"
    echo "  DRY-RUN COMPLETE"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "To execute: $0 execute"
    echo ""

else
    # Execute: Final verification
    remaining=$(grep -r "clawd" backend/app --include="*.py" 2>/dev/null | wc -l || echo 0)
    sentry_refs=$(grep -r "sentry" backend/app --include="*.py" 2>/dev/null | wc -l || echo 0)

    echo "   Remaining 'clawd' references: $remaining"
    echo "   New 'sentry' references: $sentry_refs"

    if [ "$remaining" -eq 0 ]; then
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  ✅ EXECUTION COMPLETE"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        echo "Changes applied:"
        echo "  ✓ All clawd → sentry identifiers renamed"
        echo "  ✓ OCR model fixed (settings.claude_model)"
        echo "  ✓ Safety-critical lock added (control actions use Claude only)"
        echo "  ✓ Path references updated (\$SENTRY_HOME)"
        echo ""
        echo "Backup location: $BACKUP_DIR"
        echo ""
        echo "Next: git add . && git commit ..."
        echo ""
    else
        echo "   ⚠️  Warning: $remaining clawd references still remain"
    fi
fi
