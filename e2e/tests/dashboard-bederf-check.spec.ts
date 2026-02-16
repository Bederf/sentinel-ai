import { test, expect } from '@playwright/test';

/**
 * Verify dashboard loads for bederf@gmail.com (browser check).
 * Run with: npx playwright test dashboard-bederf-check --project=chromium
 */
test.describe('Dashboard check for bederf@gmail.com', () => {
  test('login as bederf@gmail.com and see dashboard content', async ({ page }) => {
    await page.goto('/');

    // If we see email entry, log in
    const emailHeading = page.getByText('Enter your email to continue');
    if (await emailHeading.isVisible()) {
      await page.getByPlaceholder('your@email.com').fill('bederf@gmail.com');
      await page.getByRole('button', { name: 'Sign In' }).click();
      // Wait for navigation after login
      await page.waitForURL(/\//, { waitUntil: 'networkidle' });
    }

    // Wait for dashboard: either "Customize" button or KPI/section content (avoid "Loading dashboard")
    await page.waitForSelector('text=Customize', { timeout: 15000 }).catch(() => {});
    const hasCustomize = await page.getByText('Customize').isVisible();
    const hasProtectedSites = await page.getByText('Protected Sites').isVisible();
    const hasSiteProtection = await page.getByText('Site Protection').isVisible();

    expect(hasCustomize || hasProtectedSites || hasSiteProtection).toBeTruthy();

    // Should have some site cards or KPI row (dashboard not empty)
    const kpiOrCard = page.locator('[class*="grid"]').first();
    await expect(kpiOrCard).toBeVisible({ timeout: 5000 });
  });
});
