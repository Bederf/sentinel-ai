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

  // Find all sidebar buttons (they have no text but contain SVG icons)
  const navButtons = await page.evaluate(() => {
    // Get all buttons inside the sidebar/aside
    const sidebar = document.querySelector('aside');
    if (!sidebar) return [];

    const btns = sidebar.querySelectorAll('button');
    return Array.from(btns).map(b => {
      const svg = b.querySelector('svg');
      return {
        index: Array.from(sidebar.querySelectorAll('button')).indexOf(b),
        ariaLabel: b.getAttribute('aria-label'),
        hasSvg: !!svg,
        svgStroke: svg?.getAttribute('stroke'),
        text: b.innerText?.trim(),
        position: b.getBoundingClientRect()
      };
    });
  });

  console.log('=== Sidebar Nav Buttons ===');
  navButtons.forEach(b => {
    console.log(`${b.index}: aria="${b.ariaLabel}" hasSvg=${b.hasSvg} text="${b.text}" pos=(${b.position.x.toFixed(0)}, ${b.position.y.toFixed(0)})`);
  });

  // Click the second nav button (should be AI Chat based on BASE_NAV_ITEMS order)
  if (navButtons.length >= 3) {
    // dashboard=0, ai-chat=1, system-health=2...
    const aiChatBtn = navButtons[1];
    console.log(`\nClicking AI Chat button at position (${aiChatBtn.position.x}, ${aiChatBtn.position.y})`);
    await page.click(`aside button:nth-child(${aiChatBtn.index + 1})`);
    await page.waitForTimeout(2000);

    // Check what's on screen now
    const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 1500));
    console.log('\n=== Page After Click ===');
    console.log(bodyText);

    // Look for chat input
    const chatInput = await page.waitForSelector('input[placeholder*="ask" i]', { timeout: 5000 }).catch(() => null);
    if (chatInput) {
      console.log('\nFound chat input!');
      await chatInput.fill('Hello, what is the current energy consumption?');
      await page.screenshot({ path: '/opt/bms-intelligence/chat_filled.png', fullPage: false });
      console.log('Screenshot saved');
    } else {
      console.log('\nNo chat input found');
    }
  }

  await browser.close();
})();