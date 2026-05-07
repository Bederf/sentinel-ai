const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // Navigate to the login page
  await page.goto('https://bms.sentinel-ai.co.za/login');
  await page.waitForLoadState('networkidle');

  console.log('Page title:', await page.title());

  // Fill login form
  await page.fill('input[type="email"]', 'bederf@gmail.com');
  await page.fill('input[type="password"]', process.env.PASSWORD || '');

  // Click login button
  await page.click('button[type="submit"]');

  // Wait for redirect
  await page.waitForURL('**/buildings/**', { timeout: 10000 });

  // Navigate to site-002 buildings page
  await page.goto('https://bms.sentinel-ai.co.za/buildings/site-002');
  await page.waitForLoadState('networkidle');

  console.log('Current URL:', page.url());

  // Click the Space tab
  const spaceTab = page.locator('text=Space').first();
  if (await spaceTab.isVisible()) {
    await spaceTab.click();
    console.log('Clicked Space tab');
  } else {
    console.log('Space tab not found, checking available tabs...');
    const tabs = await page.locator('[role="tab"]').allTextContents();
    console.log('Available tabs:', tabs);
  }

  await browser.close();
  console.log('Done');
})();