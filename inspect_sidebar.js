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
  await page.waitForTimeout(8000);

  // Get sidebar elements
  const sidebarInfo = await page.evaluate(() => {
    // Try to find sidebar by common selectors
    const sidebarSelectors = [
      '[class*="sidebar"]', '[class*="SidePanel"]', '[class*="side-panel"]',
      '[class*="nav"]', '[class*="menu"]', 'aside', 'nav'
    ];

    const results = {};

    // Check for fixed/absolute positioned elements (common sidebar pattern)
    const positioned = document.querySelectorAll('[style*="position: fixed"], [style*="position: absolute"]');
    results.positionedElements = Array.from(positioned).slice(0, 10).map(el => ({
      tag: el.tagName,
      classes: el.className,
      text: el.innerText?.substring(0, 100),
      style: Array.from(el.style).slice(0, 5)
    }));

    // Check for SVG icons
    const svgs = document.querySelectorAll('svg');
    results.svgCount = svgs.length;
    results.firstFewSvgs = Array.from(svgs).slice(0, 15).map(s => ({
      parent: s.parentElement?.tagName + '.' + s.parentElement?.className?.split(' ')[0],
      width: s.getAttribute('width'),
      height: s.getAttribute('height'),
      viewBox: s.getAttribute('viewBox'),
      stroke: s.getAttribute('stroke')
    }));

    // Check for icon buttons
    const iconBtns = document.querySelectorAll('button[aria-label], button[class*="icon"], button[class*="nav"]');
    results.iconButtons = Array.from(iconBtns).slice(0, 15).map(btn => ({
      ariaLabel: btn.getAttribute('aria-label'),
      text: btn.innerText?.substring(0, 50),
      classes: btn.className?.substring(0, 100)
    }));

    // Get body layout
    const body = document.body.getBoundingClientRect();
    results.viewport = { width: body.width, height: body.height };

    // Check left side elements
    const leftElements = document.evaluate(
      '//*[contains(@class,"left") or contains(@class,"sidebar") or contains(@class,"nav")]//button | //aside//button | //nav//button',
      document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
    );
    results.leftButtons = [];
    for (let i = 0; i < leftElements.snapshotLength && i < 20; i++) {
      const el = leftElements.snapshotItem(i);
      results.leftButtons.push({
        text: el.innerText?.substring(0, 50),
        ariaLabel: el.getAttribute('aria-label'),
        classes: el.className?.substring(0, 80)
      });
    }

    return results;
  });

  console.log('=== SIDEBAR ANALYSIS ===');
  console.log(JSON.stringify(sidebarInfo, null, 2));

  await browser.close();
})();