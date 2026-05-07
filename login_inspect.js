const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  page.setViewportSize({ width: 1920, height: 1080 });

  const consoleMessages = [];
  const errors = [];
  const warnings = [];

  // Capture console messages with type
  page.on('console', msg => {
    const type = msg.type().toUpperCase();
    const text = msg.text();
    consoleMessages.push({ type, text: text.substring(0, 500), timestamp: Date.now() });
    if (type === 'ERROR') {
      errors.push(text.substring(0, 500));
      console.log(`[ERROR]: ${text.substring(0, 300)}`);
    } else if (type === 'WARNING') {
      warnings.push(text.substring(0, 500));
      console.log(`[WARNING]: ${text.substring(0, 300)}`);
    }
  });

  // Capture page errors
  page.on('pageerror', err => {
    errors.push(`PAGE ERROR: ${err.message}`);
    console.log(`[PAGE ERROR]: ${err.message}`);
  });

  // Capture request failures
  page.on('requestfailed', request => {
    console.log(`[FAILED REQUEST]: ${request.url().substring(0, 200)} - ${request.failure().errorText}`);
  });

  // Capture all responses
  page.on('response', response => {
    const url = response.url();
    const status = response.status();
    if (status >= 400) {
      console.log(`[HTTP ${status}]: ${url.substring(0, 200)}`);
    }
  });

  console.log('Navigating to login page...');
  const startTime = Date.now();
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded', timeout: 30000 });
  console.log(`Page loaded in ${Date.now() - startTime}ms`);

  // Wait for React to render
  await page.waitForTimeout(3000);

  // Enter email
  console.log('\nFilling email...');
  const emailInput = await page.waitForSelector('input[type="email"]', { timeout: 10000 });
  await emailInput.fill('bederf@gmail.com');

  // Click sign in
  console.log('Clicking Sign In...');
  const signInBtn = await page.waitForSelector('button:has-text("Sign In")', { timeout: 5000 });
  await signInBtn.click();

  // Wait for response
  console.log('Waiting for auth...');
  await page.waitForTimeout(8000);

  // Check what's on screen now
  const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 2000));
  console.log('\n--- Current Page Content ---');
  console.log(bodyText);

  // Check for sensitive data in localStorage/sessionStorage
  const storage = await page.evaluate(() => {
    const data = {};
    try {
      Object.keys(localStorage).forEach(k => {
        // Mask sensitive values
        if (k.includes('token') || k.includes('key') || k.includes('secret') || k.includes('auth')) {
          const v = localStorage.getItem(k);
          data[k] = v ? v.substring(0, 20) + '...' : null;
        } else if (k === 'sentinel_user') {
          const v = localStorage.getItem(k);
          try {
            const parsed = JSON.parse(v);
            // Mask sensitive fields
            if (parsed) {
              const masked = { ...parsed };
              if (masked.email) masked.email = masked.email.replace(/(.{2}).*(@.*)/, '$1***$2');
              data[k] = JSON.stringify(masked);
            }
          } catch { data[k] = '***'; }
        } else {
          data[k] = localStorage.getItem(k);
        }
      });
    } catch(e) {}
    return data;
  });
  console.log('\n--- Storage (sensitive masked) ---');
  console.log(JSON.stringify(storage, null, 2));

  // Summary
  console.log('\n=== SECURITY SUMMARY ===');
  console.log(`Errors: ${errors.length}`);
  console.log(`Warnings: ${warnings.length}`);
  console.log(`Console messages: ${consoleMessages.length}`);

  if (errors.length > 0) {
    console.log('\nERRORS:');
    errors.forEach((e, i) => console.log(`${i+1}. ${e.substring(0, 200)}`));
  }

  if (warnings.length > 0) {
    console.log('\nWARNINGS:');
    warnings.forEach((w, i) => console.log(`${i+1}. ${w.substring(0, 200)}`));
  }

  // Check for sensitive info leaks
  const sensitivePatterns = ['password', 'secret', 'token', 'api_key', 'apikey', 'bearer', 'authorization'];
  const leaked = consoleMessages.filter(m =>
    sensitivePatterns.some(p => m.text.toLowerCase().includes(p)) ||
    m.text.includes('sk-') || m.text.includes('Bearer')
  );
  if (leaked.length > 0) {
    console.log('\n⚠️ POTENTIAL SENSITIVE DATA LEAK:');
    leaked.forEach(l => console.log(`  ${l.type}: ${l.text.substring(0, 150)}`));
  } else {
    console.log('\n✓ No obvious sensitive data leaks detected');
  }

  await browser.close();
  console.log('\nDone!');
})();
