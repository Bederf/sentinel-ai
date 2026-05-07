const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  page.setDefaultTimeout(90000);

  // Login fresh
  await page.goto('https://bms.sentinel-ai.co.za', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(25000);
  await page.fill('input[type="email"]', 'bederf@gmail.com');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(20000);
  
  console.log('Logged in, URL:', page.url());

  // Navigate to buildings
  await page.goto('https://bms.sentinel-ai.co.za/buildings/site-002');
  
  // Wait for FULL load - not just INITIALIZING gone, but actual content
  console.log('Waiting for page to fully load...');
  await page.waitForFunction(() => {
    const text = document.body.innerText;
    return !text.includes('Loading site details') && 
           !text.includes('INITIALIZING') &&
           (text.includes('Overview') || text.includes('EQUIPMENT'));
  }, { timeout: 60000 });
  
  console.log('Page fully loaded');
  console.log('URL:', page.url());
  
  const body = await page.locator('body').innerText();
  
  // Find where Space tab is and click it
  const spaceIdx = body.indexOf('Space');
  if (spaceIdx > -1) {
    console.log('Space found in body at index', spaceIdx);
    console.log('Context:', body.substring(spaceIdx, spaceIdx + 200));
  }
  
  // Click Space tab button
  console.log('\nClicking Space tab button...');
  const spaceBtn = page.locator('button:has-text("Space")').first();
  if (await spaceBtn.isVisible()) {
    await spaceBtn.click();
    await page.waitForTimeout(5000);
    console.log('After Space click, URL:', page.url());
    const newBody = await page.locator('body').innerText();
    
    // Check for Space Optimization content
    if (newBody.includes('Space Optimization')) {
      console.log('✓ Space Optimization page loaded');
    }
    if (newBody.includes('Total Sessions') || newBody.includes('Focus Rooms')) {
      console.log('✓ Focus Rooms content visible');
    }
    if (newBody.includes('Concierge')) {
      console.log('✓ Concierge content visible');
    }
    if (newBody.includes('FR25') || newBody.includes('FR')) {
      console.log('✓ FR25 (focus room) visible');
    }
    
    console.log('\nBody after Space click (1000 chars):');
    console.log(newBody.substring(0, 1000));
  } else {
    console.log('Space button not visible');
    console.log('Body:', body.substring(0, 500));
  }
  
  await browser.close();
})();
