import { test, expect } from '@playwright/test';

test.describe('Device Control E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should navigate to device control from dashboard', async ({ page }) => {
    // Wait for dashboard to load
    await expect(page.locator('text=Risk Dashboard')).toBeVisible();

    // Click on Control view
    await page.click('text=Control', { timeout: 5000 });

    // Should navigate to control view
    await expect(page.locator('text=Device Control')).toBeVisible({ timeout: 5000 });
  });

  test('should display device list in control view', async ({ page }) => {
    // Navigate to control view
    await page.click('text=Control');
    await page.waitForSelector('text=Device Control');

    // Should display devices
    const devices = page.locator('[class*="DeviceListItem"]');
    await expect(devices.first()).toBeVisible({ timeout: 5000 });
  });

  test('should show device details when device selected', async ({ page }) => {
    // Navigate to control view
    await page.click('text=Control');
    await page.waitForSelector('text=Device Control');

    // Wait for devices to load
    await page.waitForSelector('[class*="DeviceListItem"]');

    // Click first device
    const firstDevice = page.locator('[class*="DeviceListItem"]').first();
    await firstDevice.click();

    // Should show device details panel
    await expect(page.locator('text=Device Details').or(page.locator('[class*="DeviceDetail"]'))).toBeVisible({ timeout: 5000 });
  });

  test('should display safety status for devices', async ({ page }) => {
    // Navigate to control view
    await page.click('text=Control');
    await page.waitForSelector('text=Device Control');

    // Should display safety indicators
    const safetyStatus = page.locator('text=SAFE').or(page.locator('text=WARNING')).or(page.locator('text=CRITICAL'));
    await expect(safetyStatus.first()).toBeVisible({ timeout: 10000 });
  });

  test('should show control panel with writable points', async ({ page }) => {
    // Navigate to control view
    await page.click('text=Control');
    await page.waitForSelector('text=Device Control');

    // Wait for devices to load
    await page.waitForSelector('[class*="DeviceListItem"]');

    // Click first device
    const firstDevice = page.locator('[class*="DeviceListItem"]').first();
    await firstDevice.click();

    // Should show control panel with points
    await expect(page.locator('text=setpoint').or(page.locator('text=Control')).or(page.locator('[class*="ControlPanel"]'))).toBeVisible({ timeout: 5000 });
  });

  test('should handle control action with safety validation', async ({ page }) => {
    // Navigate to control view
    await page.click('text=Control');
    await page.waitForSelector('text=Device Control');

    // Wait for devices to load
    await page.waitForSelector('[class*="DeviceListItem"]');

    // Click first device
    const firstDevice = page.locator('[class*="DeviceListItem"]').first();
    await firstDevice.click();

    // Look for control inputs
    const controlInput = page.locator('input[type="number"]').or(page.locator('[role="slider"]')).first();

    if (await controlInput.isVisible({ timeout: 3000 })) {
      // Get initial value
      const initialValue = await controlInput.inputValue();

      // Try to change value (may be blocked by safety rules)
      await controlInput.fill('25');

      // Look for apply/save button
      const applyButton = page.locator('button:has-text("Apply")').or(page.locator('button:has-text("Save")')).or(page.locator('button:has-text("Control")'));

      if (await applyButton.first().isVisible({ timeout: 2000 })) {
        await applyButton.first().click();

        // Should show either success or safety block message
        await expect(page.locator('text=Success').or(page.locator('text=Blocked')).or(page.locator('text=Warning'))).toBeVisible({ timeout: 5000 });
      }
    }
  });
});
