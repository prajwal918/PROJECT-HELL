const puppeteer = require('puppeteer-core');
const fs = require('fs');

(async () => {
    try {
        // Connect to the running Chrome instance using the default debugging port
        // Browser MCP usually starts Chrome with remote debugging on port 9222
        const response = await fetch('http://127.0.0.1:9222/json/version');
        const data = await response.json();
        
        const browser = await puppeteer.connect({
            browserWSEndpoint: data.webSocketDebuggerUrl,
            defaultViewport: null
        });

        const pages = await browser.pages();
        let page = pages[0];

        // 1. Get Account ID from app.deriv.com
        console.log("Navigating to app.deriv.com...");
        await page.goto('https://app.deriv.com/', {waitUntil: 'networkidle2'});
        
        // Wait for the balance dropdown to be visible
        await page.waitForSelector('.acc-info__balance', {timeout: 10000});
        await page.click('.acc-info__balance');
        
        await page.waitForSelector('.acc-switcher__account', {timeout: 5000});
        
        const accountId = await page.evaluate(() => {
            const el = document.querySelector('.acc-switcher__account .acc-switcher__loginid');
            return el ? el.innerText.trim() : null;
        });
        
        console.log("Found Account ID:", accountId);

        // 2. Get PAT token from developers.deriv.com
        console.log("Navigating to developers.deriv.com...");
        await page.goto('https://developers.deriv.com/dashboard/tokens/', {waitUntil: 'networkidle2'});
        
        // We can't easily extract a token that is hidden (***), so we generate a new one
        console.log("Generating new token...");
        await page.waitForSelector('.token-creation', {timeout: 10000});
        
        // Check Read and Trade
        await page.evaluate(() => {
            document.querySelectorAll('input[type="checkbox"]').forEach(cb => {
                if (cb.value === 'read' || cb.value === 'trade') {
                    if (!cb.checked) cb.click();
                }
            });
        });
        
        // Enter name
        await page.type('input[placeholder="Token name"]', 'Prophet100');
        await page.click('button[type="submit"]'); // Assuming Create button
        
        await page.waitForTimeout(3000); // Wait for API
        
        // Read the newest token
        const tokens = await page.evaluate(() => {
            const rows = document.querySelectorAll('.token-table tbody tr');
            if (rows.length === 0) return null;
            return rows[0].innerText;
        });
        
        console.log("Tokens found:", tokens);
        
        await browser.disconnect();
        
    } catch (e) {
        console.error("Error:", e);
    }
})();
