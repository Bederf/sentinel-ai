const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setViewportSize({ width: 1920, height: 1080 });

  // Capture console messages
  page.on('console', msg => {
    console.log(`[CONSOLE ${msg.type().toUpperCase()}]: ${msg.text().substring(0, 500)}`);
  });

  // Capture network requests
  const networkCalls = [];
  page.on('request', request => {
    networkCalls.push({
      url: request.url().substring(0, 200),
      method: request.method()
    });
  });

  // Capture failed requests
  page.on('requestfailed', request => {
    console.log(`[FAILED]: ${request.url().substring(0, 300)} - ${request.failure().errorText}`);
  });

  const url = process.argv[2] || 'https://bms.sentinel-ai.co.za';
  console.log('Navigating to:', url);

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });

  // Wait a bit for React to render
  await page.waitForTimeout(10000);

  // Check what API calls were made
  console.log('\n--- Network Requests Made ---');
  const apiCalls = networkCalls.filter(r => r.url.includes('/api/') || r.url.includes('/rest/'));
  apiCalls.forEach(r => console.log(`${r.method}: ${r.url}`));

  // Check localStorage/sessionStorage for clues
  const storage = await page.evaluate(() => {
    const sess = {};
    try {
      Object.keys(sessionStorage).forEach(k => { sess[k] = sessionStorage.getItem(k); });
    } catch(e) {}
    return sess;
  });
  console.log('\n--- SessionStorage ---');
  console.log(JSON.stringify(storage, null, 2));

  // Check for any loading indicator state
  const pageState = await page.evaluate(() => {
    const root = document.getElementById('root');
    return {
      rootHTML: root ? root.innerHTML.substring(0, 500) : 'no root',
      bodyText: document.body.innerText.substring(0, 500)
    };
  });
  console.log('\n--- Page State ---');
  console.log(JSON.stringify(pageState, null, 2));

  await browser.close();
})();
