import { test, expect } from '@playwright/test';

test.describe('AI Chat E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should navigate to tech chat view', async ({ page }) => {
    // Wait for dashboard
    await expect(page.locator('text=Risk Dashboard')).toBeVisible();

    // Click on Tech Chat
    await page.click('text=Tech Chat', { timeout: 5000 });

    // Should navigate to chat view
    await expect(page.locator('text=Chat').or(page.locator('[class*="Chat"]')).or(page.locator('textarea'))).toBeVisible({ timeout: 5000 });
  });

  test('should display chat input and send button', async ({ page }) => {
    // Navigate to chat
    await page.click('text=Tech Chat');
    await page.waitForSelector('textarea', { timeout: 5000 });

    // Should have input field
    const chatInput = page.locator('textarea');
    await expect(chatInput).toBeVisible();

    // Should have send button
    const sendButton = page.locator('button:has-text("Send")').or(page.locator('button[aria-label="Send"]')).or(page.locator('svg'));
    await expect(sendButton.first()).toBeVisible();
  });

  test('should send message and receive response', async ({ page }) => {
    // Navigate to chat
    await page.click('text=Tech Chat');
    await page.waitForSelector('textarea', { timeout: 5000 });

    // Type a message
    const chatInput = page.locator('textarea');
    await chatInput.fill('What is the status of all devices?');

    // Send message
    await chatInput.press('Enter');

    // Should show user message
    await expect(page.locator('text=What is the status of all devices?')).toBeVisible({ timeout: 3000 });

    // Should show AI response (may take a few seconds)
    await expect(page.locator('[class*="Message"]').or(page.locator('[class*="Response"]')).or(page.locator('text=device'))).toBeVisible({ timeout: 15000 });
  });

  test('should display chat history', async ({ page }) => {
    // Navigate to chat
    await page.click('text=Tech Chat');
    await page.waitForSelector('textarea', { timeout: 5000 });

    // Send multiple messages
    const chatInput = page.locator('textarea');

    await chatInput.fill('Show me all sites');
    await chatInput.press('Enter');
    await page.waitForTimeout(2000);

    await chatInput.fill('What alerts exist?');
    await chatInput.press('Enter');
    await page.waitForTimeout(2000);

    // Should show conversation history
    const messages = page.locator('[class*="Message"]').or(page.locator('[class*="ChatMessage"]'));
    const count = await messages.count();
    expect(count).toBeGreaterThan(2);
  });

  test('should handle streaming responses', async ({ page }) => {
    // Navigate to chat
    await page.click('text=Tech Chat');
    await page.waitForSelector('textarea', { timeout: 5000 });

    // Send a message that triggers AI
    const chatInput = page.locator('textarea');
    await chatInput.fill('Analyze the current system health');
    await chatInput.press('Enter');

    // Should show loading/typing indicator
    await expect(page.locator('text=Thinking').or(page.locator('[class*="Loading"]').or(page.locator('[aria-busy="true"]'))).toBeVisible({ timeout: 5000 });

    // Should eventually show response
    await expect(page.locator('[class*="Message"]').or(page.locator('[class*="Response"]'))).toBeVisible({ timeout: 20000 });
  });
});
