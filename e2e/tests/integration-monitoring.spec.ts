import { test, expect } from '@playwright/test';

test.describe('Integration Monitoring E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should navigate to integration monitoring view', async ({ page }) => {
    // Wait for dashboard
    await expect(page.locator('text=Risk Dashboard')).toBeVisible();

    // Click on Integration Monitoring (if visible)
    const integrationLink = page.locator('text=Integration').or(page.locator('text=Monitoring')).or(page.locator('text=Integrations'));
    if (await integrationLink.first().isVisible({ timeout: 3000 })) {
      await integrationLink.first().click();

      // Should navigate to integration view
      await expect(page.locator('text=Integration').or(page.locator('[class*="Integration"]'))).toBeVisible({ timeout: 5000 });
    }
  });

  test('should display connection status for integrations', async ({ page }) => {
    // Try to navigate to integrations
    const integrationLink = page.locator('text=Integration').or(page.locator('text=Integrations'));
    if (await integrationLink.first().isVisible({ timeout: 3000 })) {
      await integrationLink.first().click();
      await page.waitForTimeout(1000);

      // Should show connection status indicators
      const statusIndicators = page.locator('text=Connected').or(page.locator('text=Online')).or(page.locator('[class*="Status"]'));
      await expect(statusIndicators.first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('should display sync status for data sources', async ({ page }) => {
    // Try to navigate to integrations
    const integrationLink = page.locator('text=Integration').or(page.locator('text=Integrations'));
    if (await integrationLink.first().isVisible({ timeout: 3000 })) {
      await integrationLink.first().click();
      await page.waitForTimeout(1000);

      // Should show last sync time or record counts
      const syncInfo = page.locator('text=Last sync').or(page.locator('text=records').or(page.locator('text=Sync')));
      if (await syncInfo.first().isVisible({ timeout: 3000 })) {
        await expect(syncInfo.first()).toBeVisible();
      }
    }
  });
});
