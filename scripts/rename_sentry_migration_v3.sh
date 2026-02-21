#!/bin/bash
# Stage 6 Addendum: Rename remaining sentry references to sentry
# This script fixes all remaining sentry references found post-Stage 5

set -e

cd /opt/bms-intelligence

echo "🔍 Stage 6 Addendum: Rename remaining SENTRY → SENTRY references"
echo ""
echo "Found 54 sentry references in backend code"
echo "This script will rename them all to sentry"
echo ""

# Backup first
BACKUP_DIR="backups/sentry_to_sentry_v3_$(date +%s)"
mkdir -p "$BACKUP_DIR"

echo "📦 Creating backup in $BACKUP_DIR..."
cp -r backend/app "$BACKUP_DIR/"

echo ""
echo "🔄 Applying renames..."
echo ""

# Pattern 1: sentry_integration → sentry_integration (directory/module name)
echo "1. Renaming sentry_integration → sentry_integration..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentry_integration/sentry_integration/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i 's/sentry-integration/sentry-integration/g' {} \;
echo "   ✓ Updated file references"

# Pattern 2: sentrybot → sentrybot (CLI tool name)
echo "2. Renaming sentrybot → sentrybot..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentrybot/sentrybot/g' {} \;
echo "   ✓ Updated CLI references"

# Pattern 3: sentry_api_url → sentry_api_url
echo "3. Renaming sentry_api_url → sentry_api_url..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentry_api_url/sentry_api_url/g' {} \;
echo "   ✓ Updated URL variable names"

# Pattern 4: sentry_alert → sentry_alert
echo "4. Renaming sentry_alert → sentry_alert..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentry_alert/sentry_alert/g' {} \;
echo "   ✓ Updated alert variable names"

# Pattern 5: sentry_message → sentry_message
echo "5. Renaming sentry_message → sentry_message..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentry_message/sentry_message/g' {} \;
echo "   ✓ Updated message variable names"

# Pattern 6: sentry_notification → sentry_notification
echo "6. Renaming sentry_notification → sentry_notification..."
find backend/app -type f -name "*.py" -exec sed -i 's/sentry_notification/sentry_notification/g' {} \;
echo "   ✓ Updated notification references"

# Pattern 7: add_sentry_notification_job → add_sentry_notification_job
echo "7. Renaming add_sentry_notification_job → add_sentry_notification_job..."
find backend/app -type f -name "*.py" -exec sed -i 's/add_sentry_notification_job/add_sentry_notification_job/g' {} \;
echo "   ✓ Updated scheduler job names"

# Pattern 8: format_sentry_message → format_sentry_message
echo "8. Renaming format_sentry_message → format_sentry_message..."
find backend/app -type f -name "*.py" -exec sed -i 's/format_sentry_message/format_sentry_message/g' {} \;
echo "   ✓ Updated formatter method names"

# Pattern 9: /api/sentry → /api/sentry (API paths)
echo "9. Renaming /api/sentry → /api/sentry..."
find backend/app -type f -name "*.py" -exec sed -i 's|/api/sentry|/api/sentry|g' {} \;
echo "   ✓ Updated API paths"

# Pattern 10: "sentry" in comments and strings (context-specific)
echo "10. Updating sentry references in comments and docstrings..."
find backend/app -type f -name "*.py" -exec sed -i 's/Sentry/Sentry/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i 's/SENTRY/SENTRY/g' {} \;
echo "   ✓ Updated documentation"

# Pattern 11: channel: "sentry" → channel: "sentry"
echo "11. Updating notification channel names..."
find backend/app -type f -name "*.py" -exec sed -i 's/"channel": "sentry"/"channel": "sentry"/g' {} \;
find backend/app -type f -name "*.py" -exec sed -i "s/'channel': 'sentry'/'channel': 'sentry'/g" {} \;
echo "   ✓ Updated channel references"

# Pattern 12: /sentry/phyphox → /sentry/phyphox (endpoint paths)
echo "12. Renaming endpoint paths /sentry → /sentry..."
find backend/app -type f -name "*.py" -exec sed -i 's|"/sentry/|"/sentry/|g' {} \;
echo "   ✓ Updated endpoint paths"

echo ""
echo "✅ All renames complete!"
echo ""
echo "📊 Verification:"
echo ""

# Show before/after counts
BEFORE=$(grep -r "sentry" backend/app --include="*.py" | wc -l)
AFTER=$(grep -r "sentry" backend/app --include="*.py" | grep -v "Sentry" | wc -l)

echo "Remaining 'sentry' references: $BEFORE"
echo "New 'sentry' references: $AFTER"
echo ""

if [ $BEFORE -eq 0 ]; then
    echo "🎉 SUCCESS! All sentry references have been renamed to sentry"
else
    echo "⚠️  $BEFORE sentry references still remain - check manually:"
    grep -rn "sentry" backend/app --include="*.py" | head -10
fi

echo ""
echo "📋 Files modified:"
echo "   - 54 sentry → sentry references"
echo "   - Updated variable names, API paths, comments"
echo ""
echo "💾 Backup saved to: $BACKUP_DIR"
echo "   Restore with: cp -r $BACKUP_DIR/app/* backend/app/"
echo ""
