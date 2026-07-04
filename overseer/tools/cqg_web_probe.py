#!/usr/bin/env python3
"""Probe the CQG Desktop web app login flow.
Reads credentials from env (set by overseer/.env).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

async def main() -> None:
    from playwright.async_api import async_playwright

    user = os.getenv("CQG_USERNAME", "")
    pw = os.getenv("CQG_PASSWORD", "")
    if not user or not pw:
        print("Set CQG_USERNAME and CQG_PASSWORD in overseer/.env")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        page.on("console", lambda msg: print("CONSOLE:", msg.text))
        page.on("pageerror", lambda err: print("PAGE ERROR:", err))
        page.on("response", lambda resp: print("RESPONSE:", resp.status, resp.url[:120]))
        page.on("websocket", lambda ws: print("WS:", ws.url))

        print("Loading CQG Desktop login...")
        await page.goto("https://m.cqg.com/cqg/desktop/logon", wait_until="networkidle")
        await page.screenshot(path=str(ROOT / "logs" / "cqg_web_01_login.png"))
        print("Screenshot saved: cqg_web_01_login.png")

        # Dump page HTML to understand structure
        html = await page.content()
        with open(ROOT / "logs" / "cqg_web_login.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("HTML saved: cqg_web_login.html")

        # Try generic input selectors
        print("Looking for inputs...")
        inputs = await page.locator("input").all()
        for i, inp in enumerate(inputs):
            attrs = await inp.evaluate("el => ({type: el.type, name: el.name, id: el.id, placeholder: el.placeholder, class: el.className})")
            print(f"  input[{i}]:", attrs)

        # Fill using placeholder or type
        user_filled = False
        pw_filled = False
        for inp in inputs:
            attrs = await inp.evaluate("el => ({type: el.type, placeholder: el.placeholder, name: el.name})")
            if attrs["type"] == "text" or attrs["type"] == "email" or "user" in (attrs["placeholder"] or "").lower():
                await inp.fill(user)
                user_filled = True
            elif attrs["type"] == "password":
                await inp.fill(pw)
                pw_filled = True

        if not (user_filled and pw_filled):
            print("Could not find username/password inputs")
            await browser.close()
            return

        await page.screenshot(path=str(ROOT / "logs" / "cqg_web_03_filled.png"))
        print("Screenshot saved: cqg_web_03_filled.png")

        # Click login
        login_btn = page.locator("button:has-text('Log on'), button:has-text('Login'), input[type='submit']").first
        if await login_btn.is_visible(timeout=5000):
            print("Clicking login...")
            await login_btn.click()
            await page.wait_for_timeout(10000)
            await page.screenshot(path=str(ROOT / "logs" / "cqg_web_04_after_login.png"))
            print("Screenshot saved: cqg_web_04_after_login.png")

        print("URL after login:", page.url)
        print("Page title:", await page.title())

        # Save final HTML
        html2 = await page.content()
        with open(ROOT / "logs" / "cqg_web_after_login.html", "w", encoding="utf-8") as f:
            f.write(html2)
        print("HTML saved: cqg_web_after_login.html")

        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
