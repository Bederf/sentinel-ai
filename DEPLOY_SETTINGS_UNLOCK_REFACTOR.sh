#!/bin/bash

# Settings Page Unlock Refactor - Deployment Script
# This script deploys the page-level password protection for Settings page

set -e

echo "════════════════════════════════════════════════════════════════════"
echo "         SETTINGS PAGE UNLOCK REFACTOR - DEPLOYMENT"
echo "════════════════════════════════════════════════════════════════════"
echo ""

# Check if running on production
if [ ! -f "/etc/hostname" ] || ! grep -q "production\|bms" /etc/hostname 2>/dev/null; then
    echo "⚠️  Warning: This script should be run on the production BMS server"
    echo "Continuing anyway..."
fi

echo "📋 COMMIT DETAILS"
echo "─────────────────────────────────────────────────────────────────────"
echo "Commit: 57f0bfe0"
echo "Message: refactor(settings): Move password protection from toggle-level to page-level"
echo ""
echo "Changes:"
echo "  • Replaced section-level unlock states with single page-level unlock"
echo "  • Moved unlock button from Feature Access to Settings page header"
echo "  • Removed individual unlock buttons from Safety Rules + Feature Access"
echo "  • All settings now protected by single password"
echo ""

echo "📦 DEPLOYMENT STEPS"
echo "─────────────────────────────────────────────────────────────────────"

echo "1️⃣  Pulling latest code..."
cd /opt/bms-intelligence
git pull origin main
if [ $? -eq 0 ]; then
    echo "   ✅ Git pull successful"
else
    echo "   ❌ Git pull failed"
    exit 1
fi
echo ""

echo "2️⃣  Rebuilding frontend..."
cd /opt/bms-intelligence/frontend
npm run build
if [ $? -eq 0 ]; then
    echo "   ✅ Frontend build successful"
else
    echo "   ❌ Frontend build failed"
    exit 1
fi
echo ""

echo "3️⃣  Restarting frontend service..."
sudo systemctl restart sentinel-frontend
sleep 2

if systemctl is-active --quiet sentinel-frontend; then
    echo "   ✅ Frontend service restarted successfully"
else
    echo "   ❌ Frontend service failed to start"
    exit 1
fi
echo ""

echo "4️⃣  Verifying services..."
echo ""
echo "   Backend Status:"
sudo systemctl status sentinel-backend --no-pager | head -3
echo ""
echo "   Frontend Status:"
sudo systemctl status sentinel-frontend --no-pager | head -3
echo ""

echo "✅ DEPLOYMENT COMPLETE"
echo "════════════════════════════════════════════════════════════════════"
echo ""
echo "🎯 VERIFICATION STEPS"
echo "─────────────────────────────────────────────────────────────────────"
echo ""
echo "1. Open Settings page in browser:"
echo "   https://bms.aimthelaw.co.za/settings"
echo ""
echo "2. Demo user unlock button should be at TOP of Settings page"
echo "   (not on individual Feature Access section anymore)"
echo ""
echo "3. Click 'Unlock to Edit' button"
echo "   • Should show single password modal"
echo "   • Title: 'Unlock Settings Page'"
echo ""
echo "4. After unlocking, you should be able to edit:"
echo "   • Safety Rules (no separate unlock needed)"
echo "   • Feature Access toggles (no separate unlock needed)"
echo "   • Other settings"
echo ""
echo "5. Click 'Lock Settings' at top of page to lock again"
echo ""
echo "✨ Benefits:"
echo "   • Single password protects entire Settings page"
echo "   • Cleaner UI without redundant unlock buttons"
echo "   • Simpler user workflow"
echo ""
echo "📞 If something goes wrong:"
echo "   • Check browser console (F12) for errors"
echo "   • Verify frontend is running: systemctl status sentinel-frontend"
echo "   • Check frontend logs: journalctl -u sentinel-frontend -n 50"
echo ""
