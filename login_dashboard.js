const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setViewportSize({ width: 1920, height: 1080 });

  console.log('Logging in...');
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);

  await page.fill('input[type="email"]', 'bederf@gmail.com');
  await page.click('button:has-text("Sign In")');

  console.log('Waiting for dashboard...');
  await page.waitForTimeout(8000);

  console.log('Taking screenshot...');
  await page.screenshot({ path: '/opt/bms-intelligence/dashboard.png', fullPage: true });

  // Get page title and main content
  const title = await page.title();
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 1500));

  console.log('\nTitle:', title);
  console.log('\n--- Page Text ---');
  console.log(bodyText);

  console.log('\nScreenshot saved to /opt/bms-intelligence/dashboard.png');

  await browser.close();
})();