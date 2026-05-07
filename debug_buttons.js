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

  // Get all buttons and their aria-labels
  const buttons = await page.evaluate(() => {
    const btns = document.querySelectorAll('button');
    return Array.from(btns).map(b => ({
      ariaLabel: b.getAttribute('aria-label'),
      text: b.innerText?.substring(0, 50),
      classes: b.className?.split(' ').slice(0, 5).join(' ')
    }));
  });
  console.log('=== All buttons ===');
  buttons.forEach((b, i) => console.log(`${i}: aria="${b.ariaLabel}" text="${b.text}" class="${b.classes}"`));

  // Get page text
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 1000));
  console.log('\n=== Page Text ===');
  console.log(bodyText);

  await browser.close();
})();
