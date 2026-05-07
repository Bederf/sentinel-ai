const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  // Login
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  await page.fill('input[type="email"]', 'bederf@gmail.com');
  await page.click('button:has-text("Sign In")');
  await page.waitForTimeout(6000);

  // Expand sidebar first by clicking the expand button
  console.log('Expanding sidebar...');
  await page.click('button[aria-label="Expand sidebar"]');
  await page.waitForTimeout(1000);

  // Now find and click the AI Chat button by its text
  console.log('Looking for AI Chat...');
  const aiChatBtn = await page.locator('aside button:has-text("AI Chat")');
  await aiChatBtn.click();
  console.log('Clicked AI Chat');

  await page.waitForTimeout(3000);

  // Check page content
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 2000));
  console.log('\n=== Page After Click ===');
  console.log(bodyText.substring(0, 1500));

  // Find chat input
  const chatInput = await page.locator('input[placeholder*="ask" i]').first();
  const inputCount = await page.locator('input[placeholder*="ask" i]').count();
  console.log(`\nChat input count: ${inputCount}`);

  if (inputCount > 0) {
    console.log('Found chat input!');
    await chatInput.fill('Hello, what is the current energy consumption?');
    await page.waitForTimeout(500);
    await page.screenshot({ path: '/opt/bms-intelligence/chat_filled.png', fullPage: false });
    console.log('Screenshot saved');
  }

  await browser.close();
})();