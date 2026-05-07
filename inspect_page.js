const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setViewportSize({ width: 1920, height: 1080 });

  const url = process.argv[2] || 'https://bms.sentinel-ai.co.za';
  console.log('Navigating to:', url);

  await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });

  // Get page title
  const title = await page.title();
  console.log('Title:', title);

  // Get visible text content (first 2000 chars)
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('\n--- Visible Text (first 2000 chars) ---');
  console.log(bodyText.substring(0, 2000));

  // Get main heading
  const h1 = await page.evaluate(() => {
    const el = document.querySelector('h1');
    return el ? el.textContent : 'no h1';
  });
  console.log('\nMain heading:', h1);

  // Get React root info
  const reactInfo = await page.evaluate(() => {
    const root = document.getElementById('root');
    return {
      hasRoot: !!root,
      childCount: root ? root.children.length : 0,
      firstChildTag: root && root.firstChild ? root.firstChild.tagName : 'none'
    };
  });
  console.log('React root:', JSON.stringify(reactInfo));

  // Check for any visible errors
  const errors = await page.evaluate(() => {
    const elements = document.querySelectorAll('[class*="error"], [class*="Error"], [id*="error"]');
    return Array.from(elements).slice(0, 5).map(el => ({
      tag: el.tagName,
      text: el.innerText.substring(0, 100),
      visible: el.offsetParent !== null
    }));
  });
  if (errors.length > 0) {
    console.log('\nError elements found:', JSON.stringify(errors, null, 2));
  }

  await browser.close();
  console.log('\nDone!');
})();