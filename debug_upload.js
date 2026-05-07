const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1920, height: 1080 });

  const failedRequests = [];

  page.on('requestfailed', request => {
    failedRequests.push({
      url: request.url(),
      failure: request.failure()?.errorText,
      method: request.method()
    });
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      failedRequests.push({
        url: response.url(),
        status: response.status(),
        method: response.request().method()
      });
    }
  });

  // Login
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  await page.fill('input[type="email"]', 'bederf@gmail.com');
  await page.click('button:has-text("Sign In")');
  await page.waitForTimeout(6000);

  // Go to AI Chat
  await page.click('button[aria-label="Expand sidebar"]');
  await page.waitForTimeout(500);
  await page.locator('aside button:has-text("AI Chat")').click();
  await page.waitForTimeout(2000);

  // Try to find and click upload button
  console.log('Looking for upload functionality...');

  const uploadBtn = await page.locator('button:has-text("Upload")').first();
  if (await uploadBtn.count() > 0) {
    console.log('Found Upload button');
    await uploadBtn.click();
    await page.waitForTimeout(2000);
  }

  // Report failed requests
  console.log('\n=== Failed Requests ===');
  failedRequests.forEach(r => {
    console.log(`${r.method || 'GET'} ${r.url} - ${r.status || r.failure}`);
  });

  await browser.close();
})();