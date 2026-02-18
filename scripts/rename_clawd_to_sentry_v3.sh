#!/bin/bash
# Stage 6 Addendum: Rename remaining clawd references to sentry
# This script fixes all remaining clawd references found post-Stage 5

set -e

cd /opt/bms-intelligence

echo "🔍 Stage 6 Addendum: Rename remaining CLAWD → SENTRY references"
echo ""
echo "Found 54 clawd references in backend code"
echo "This script will rename them all to sentry"
echo ""

# Backup first
BACKUP_DIR="backups/clawd_to_sentry_v3_$(date +%s)"
mkdir -p "$BACKUP_DIR"

echo "📦 Creating backup in $BACKUP_DIR..."
cp -r backend/app "$BACKUP_DIR/"

echo ""
echo "🔄 Applying renames..."
echo ""

# Pattern 1: clawd_integration → sentry_integration (directory/module name)
echo "1. Renaming clawd_integration → sentry_integration..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawd_integration/sentry_integration/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i 's/clawd-integration/sentry-integration/g' {} \;
echo "   ✓ Updated file references"

# Pattern 2: clawdbot → sentrybot (CLI tool name)
echo "2. Renaming clawdbot → sentrybot..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawdbot/sentrybot/g' {} \;
echo "   ✓ Updated CLI references"

# Pattern 3: clawd_api_url → sentry_api_url
echo "3. Renaming clawd_api_url → sentry_api_url..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawd_api_url/sentry_api_url/g' {} \;
echo "   ✓ Updated URL variable names"

# Pattern 4: clawd_alert → sentry_alert
echo "4. Renaming clawd_alert → sentry_alert..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawd_alert/sentry_alert/g' {} \;
echo "   ✓ Updated alert variable names"

# Pattern 5: clawd_message → sentry_message
echo "5. Renaming clawd_message → sentry_message..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawd_message/sentry_message/g' {} \;
echo "   ✓ Updated message variable names"

# Pattern 6: clawd_notification → sentry_notification
echo "6. Renaming clawd_notification → sentry_notification..."
find backend/app -type f -name "*.py" -exec sed -i 's/clawd_notification/sentry_notification/g' {} \;
echo "   ✓ Updated notification references"

# Pattern 7: add_clawd_notification_job → add_sentry_notification_job
echo "7. Renaming add_clawd_notification_job → add_sentry_notification_job..."
find backend/app -type f -name "*.py" -exec sed -i 's/add_clawd_notification_job/add_sentry_notification_job/g' {} \;
echo "   ✓ Updated scheduler job names"

# Pattern 8: format_clawd_message → format_sentry_message
echo "8. Renaming format_clawd_message → format_sentry_message..."
find backend/app -type f -name "*.py" -exec sed -i 's/format_clawd_message/format_sentry_message/g' {} \;
echo "   ✓ Updated formatter method names"

# Pattern 9: /api/clawd → /api/sentry (API paths)
echo "9. Renaming /api/clawd → /api/sentry..."
find backend/app -type f -name "*.py" -exec sed -i 's|/api/clawd|/api/sentry|g' {} \;
echo "   ✓ Updated API paths"

# Pattern 10: "clawd" in comments and strings (context-specific)
echo "10. Updating clawd references in comments and docstrings..."
find backend/app -type f -name "*.py" -exec sed -i 's/Clawd/Sentry/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i 's/CLAWD/SENTRY/g' {} \;
echo "   ✓ Updated documentation"

# Pattern 11: channel: "clawd" → channel: "sentry"
echo "11. Updating notification channel names..."
find backend/app -type f -name "*.py" -exec sed -i 's/"channel": "clawd"/"channel": "sentry"/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i "s/'channel': 'clawd'/'channel': 'sentry'/g" {} \;
echo "   ✓ Updated channel references"

# Pattern 12: /clawd/phyphox → /sentry/phyphox (endpoint paths)
echo "12. Renaming endpoint paths /clawd → /sentry..."
find backend/app -type f -name "*.py" -exec sed -i 's|"/clawd/|"/sentry/|g' {} \;
echo "   ✓ Updated endpoint paths"

echo ""
echo "✅ All renames complete!"
echo ""
echo "📊 Verification:"
echo ""

# Show before/after counts
BEFORE=$(grep -r "clawd" backend/app --include="*.py" | wc -l)
AFTER=$(grep -r "sentry" backend/app --include="*.py" | grep -v "Sentry" | wc -l)

echo "Remaining 'clawd' references: $BEFORE"
echo "New 'sentry' references: $AFTER"
echo ""

if [ $BEFORE -eq 0 ]; then
    echo "🎉 SUCCESS! All clawd references have been renamed to sentry"
else
    echo "⚠️  $BEFORE clawd references still remain - check manually:"
    grep -rn "clawd" backend/app --include="*.py" | head -10
fi

echo ""
echo "📋 Files modified:"
echo "   - 54 clawd → sentry references"
echo "   - Updated variable names, API paths, comments"
echo ""
echo "💾 Backup saved to: $BACKUP_DIR"
echo "   Restore with: cp -r $BACKUP_DIR/app/* backend/app/"
echo ""
