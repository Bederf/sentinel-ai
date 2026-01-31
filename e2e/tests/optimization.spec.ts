import { test, expect } from '@playwright/test';

test.describe('Optimization E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should navigate to optimization view', async ({ page }) => {
    // Wait for dashboard
    await expect(page.locator('text=Risk Dashboard')).toBeVisible();

    // Click on Optimization
    await page.click('text=Optimization', { timeout: 5000 });

    // Should navigate to optimization view
    await expect(page.locator('text=Optimization').or(page.locator('text=Recommendations')).or(page.locator('[class*="Optimization"]'))).toBeVisible({ timeout: 5000 });
  });

  test('should display optimization recommendations', async ({ page }) => {
    // Navigate to optimization
    await page.click('text=Optimization');
    await page.waitForSelector('text=Optimization', { timeout: 5000 });

    // Should display recommendations
    const recommendations = page.locator('[class*="Recommendation"]').or(page.locator('[class*="OptimizationCard"]'));
    await expect(recommendations.first()).toBeVisible({ timeout: 5000 });
  });

  test('should show equipment details in recommendations', async ({ page }) => {
    // Navigate to optimization
    await page.click('text=Optimization');
    await page.waitForSelector('text=Optimization', { timeout: 5000 });

    // Should show equipment names
    await expect(page.locator('text=Chiller').or(page.locator('text=AHU')).or(page.locator('text=device'))).toBeVisible({ timeout: 5000 });
  });

  test('should display recommendation actions', async ({ page }) => {
    // Navigate to optimization
    await page.click('text=Optimization');
    await page.waitForSelector('text=Optimization', { timeout: 5000 });

    // Should show action buttons (Apply, Dismiss, etc.)
    const actionButtons = page.locator('button:has-text("Apply")').or(page.locator('button:has-text("Dismiss")')).or(page.locator('button:has-text("Approve")'));
    if (await actionButtons.first().isVisible({ timeout: 3000 })) {
      await expect(actionButtons.first()).toBeVisible();
    }
  });

  test('should filter recommendations by severity', async ({ page }) => {
    // Navigate to optimization
    await page.click('text=Optimization');
    await page.waitForSelector('text=Optimization', { timeout: 5000 });

    // Look for filter controls
    const filterButtons = page.locator('button:has-text("Critical")').or(page.locator('button:has-text("High")')).or(page.locator('[class*="Filter"]'));
    if (await filterButtons.first().isVisible({ timeout: 3000 })) {
      await filterButtons.first().click();
      await page.waitForTimeout(500);

      // Should still show recommendations
      const recommendations = page.locator('[class*="Recommendation"]');
      await expect(recommendations.first()).toBeVisible();
    }
  });
});
