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

  // Click AI Chat
  const aiChatBtn = await page.waitForSelector('button[aria-label="AI Chat"]', { timeout: 5000 });
  await aiChatBtn.click();
  await page.waitForTimeout(2000);

  // Type in the chat input
  const chatInput = await page.waitForSelector('input[placeholder*="ask" i]', { timeout: 5000 });
  await chatInput.fill('Hello, what is the current energy consumption for today?');

  // Take screenshot before sending
  await page.screenshot({ path: '/opt/bms-intelligence/chat_before_send.png', fullPage: false });

  // Press Enter to send
  await chatInput.press('Enter');
  console.log('Message sent!');

  // Wait for response
  await page.waitForTimeout(5000);

  // Take screenshot after response
  await page.screenshot({ path: '/opt/bms-intelligence/chat_after_response.png', fullPage: false });

  // Get chat content
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 3000));
  console.log('\n=== Chat Page Content ===');
  console.log(bodyText);

  await browser.close();
})();
