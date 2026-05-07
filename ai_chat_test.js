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
  console.log('Logged in, waiting for dashboard...');
  await page.waitForTimeout(6000);

  // Click AI Chat icon (MessageSquare icon)
  console.log('Looking for AI Chat button...');
  const aiChatBtn = await page.waitForSelector('button[aria-label="AI Chat"], button:has-text("AI Chat")', { timeout: 10000 });
  await aiChatBtn.click();
  console.log('Clicked AI Chat');

  await page.waitForTimeout(3000);

  // Look for the chat input box
  console.log('Looking for chat input...');
  const inputSelectors = [
    'textarea[placeholder*="message" i]',
    'textarea[placeholder*="ask" i]',
    'textarea[placeholder*="chat" i]',
    'input[placeholder*="message" i]',
    'input[placeholder*="ask" i]',
    'input[placeholder*="chat" i]',
    'textarea',
    'input[type="text"]'
  ];

  let chatInput = null;
  for (const selector of inputSelectors) {
    try {
      const el = await page.waitForSelector(selector, { timeout: 3000 });
      if (el) {
        chatInput = el;
        console.log(`Found input with selector: ${selector}`);
        break;
      }
    } catch (e) {}
  }

  if (!chatInput) {
    console.log('No chat input found, checking page content...');
    const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 2000));
    console.log(bodyText);
  } else {
    // Type a test message
    console.log('Typing test message...');
    await chatInput.fill('Hello, what is the current energy consumption?');
    await page.waitForTimeout(1000);

    // Take screenshot
    await page.screenshot({ path: '/opt/bms-intelligence/ai_chat.png', fullPage: false });

    const currentText = await chatInput.inputValue();
    console.log('Input value:', currentText);
    console.log('Screenshot saved to /opt/bms-intelligence/ai_chat.png');
  }

  await browser.close();
})();