import { test, expect } from '@playwright/test';

test.describe('Dashboard E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to dashboard
    await page.goto('/');
  });

  test('should load dashboard and display sites', async ({ page }) => {
    // Wait for dashboard to load
    await expect(page.locator('text=Risk Dashboard')).toBeVisible();

    // Should display site cards
    await expect(page.locator('[class*="SiteCard"]').first()).toBeVisible();
  });

  test('should navigate to site detail on card click', async ({ page }) => {
    // Wait for sites to load
    await page.waitForSelector('[class*="SiteCard"]');

    // Click first site card
    const firstCard = page.locator('[class*="SiteCard"]').first();
    await firstCard.click();

    // Should navigate to site detail view
    await expect(page.locator('text=Site Details')).toBeVisible({ timeout: 5000 });
  });

  test('should display KPI cards', async ({ page }) => {
    // Wait for dashboard to load
    await page.waitForSelector('text=Risk Dashboard');

    // Should display KPI cards
    await expect(page.locator('[class*="KPICard"]').first()).toBeVisible();
  });
});
