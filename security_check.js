const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setViewportSize({ width: 1920, height: 1080 });

  const consoleMessages = [];
  const apiCalls = [];

  page.on('console', msg => {
    consoleMessages.push({ type: msg.type(), text: msg.text() });
  });

  page.on('request', request => {
    const url = request.url();
    if (url.includes('/api/') || url.includes('/rest/')) {
      apiCalls.push({ method: request.method(), url: url.replace(/token=[^&]+/g, 'token=***') });
    }
  });

  page.on('response', response => {
    const url = response.url();
    const status = response.status();
    if ((url.includes('/api/') || url.includes('/rest/')) && status >= 400) {
      console.log(`[HTTP ${status}]: ${url}`);
    }
  });

  console.log('=== LOGGING IN ===');
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(2000);

  const emailInput = await page.waitForSelector('input[type="email"]', { timeout: 10000 });
  await emailInput.fill('bederf@gmail.com');
  const signInBtn = await page.waitForSelector('button:has-text("Sign In")', { timeout: 5000 });
  await signInBtn.click();

  console.log('Waiting for dashboard...');
  await page.waitForTimeout(8000);

  // Get all console messages
  console.log('\n=== ALL CONSOLE MESSAGES ===');
  consoleMessages.forEach((m, i) => {
    console.log(`${i+1}. [${m.type.toUpperCase()}]: ${m.text.substring(0, 400)}`);
  });

  // Get all API calls made
  console.log('\n=== ALL API CALLS ===');
  apiCalls.forEach((a, i) => {
    console.log(`${i+1}. ${a.method}: ${a.url}`);
  });

  // Check for sensitive patterns in responses
  console.log('\n=== SENSITIVE DATA CHECK ===');

  // Check localStorage for tokens
  const tokenCheck = await page.evaluate(() => {
    const token = localStorage.getItem('sentinel_token');
    const refresh = localStorage.getItem('sentinel_refresh_token');
    return {
      hasToken: !!token,
      tokenPrefix: token ? token.substring(0, 30) : null,
      hasRefresh: !!refresh,
      refreshPrefix: refresh ? refresh.substring(0, 30) : null
    };
  });
  console.log('Token stored:', tokenCheck.hasToken ? `Yes (${tokenCheck.tokenPrefix}...)` : 'No');
  console.log('Refresh stored:', tokenCheck.hasRefresh ? `Yes (${tokenCheck.refreshPrefix}...)` : 'No');

  // Check if tokens are exposed in memory/console
  const sensitiveLeaks = consoleMessages.filter(m =>
    m.text.includes('sk-') ||
    m.text.includes('secret') ||
    m.text.includes('password') ||
    (m.text.includes('token') && m.text.includes('eyJ')) ||
    m.text.includes('Bearer ')
  );

  if (sensitiveLeaks.length > 0) {
    console.log('\n⚠️ SENSITIVE DATA LEAK DETECTED:');
    sensitiveLeaks.forEach(l => console.log(`  [${l.type}]: ${l.text.substring(0, 200)}`));
  } else {
    console.log('✓ No sensitive data leaks (API keys, secrets, full tokens)');
  }

  // Check for timing issues
  console.log('\n=== TIMING CHECK ===');
  const startTime = Date.now();
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded', timeout: 30000 });
  const loadTime = Date.now() - startTime;
  console.log(`Initial page load: ${loadTime}ms`);

  // Check if system clock is consistent
  const pageTime = await page.evaluate(() => {
    const now = new Date();
    return { iso: now.toISOString(), local: now.toString() };
  });
  console.log('Page time:', pageTime.iso);

  // Page errors
  const pageErrors = consoleMessages.filter(m => m.type === 'error');
  console.log(`\nPage errors: ${pageErrors.length}`);
  if (pageErrors.length > 0) {
    pageErrors.forEach(e => console.log(`  ${e.text.substring(0, 200)}`));
  }

  await browser.close();
  console.log('\nDone!');
})();