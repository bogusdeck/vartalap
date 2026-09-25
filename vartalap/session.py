import os
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from playwright.async_api import async_playwright, BrowserContext, Page, Playwright

from vartalap.settings import get_settings


@asynccontextmanager
async def get_browser_context(
    storage_state_path: Optional[str] = None,
    headless: Optional[bool] = None
) -> AsyncGenerator[BrowserContext, None]:
    """Yields an authenticated Playwright BrowserContext using storage_state.json."""
    settings = get_settings()
    state_path = storage_state_path or settings.reddit.storage_state_path
    abs_state_path = Path(state_path).resolve()
    is_headless = settings.reddit.headless if headless is None else headless

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-notifications"]
        )

        if abs_state_path.exists():
            context = await browser.new_context(storage_state=str(abs_state_path))
        else:
            # If no state file exists, create empty context with warning
            print(f"[WARNING] Storage state file '{abs_state_path}' not found. Browser will be unauthenticated.")
            context = await browser.new_context()

        try:
            yield context
        finally:
            await context.close()
            await browser.close()


@asynccontextmanager
async def get_page(
    storage_state_path: Optional[str] = None,
    headless: Optional[bool] = None,
    fast_mode: bool = True
) -> AsyncGenerator[Page, None]:
    """Yields a ready Playwright Page object from authenticated browser context."""
    async with get_browser_context(storage_state_path=storage_state_path, headless=headless) as context:
        page = await context.new_page()
        page.set_default_timeout(15000)

        if fast_mode:
            # Block images, fonts, and media for 3x faster page loads
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf,otf,mp4,webm}",
                lambda route: route.abort()
            )
        try:
            yield page
        finally:
            await page.close()


async def run_one_time_login(storage_state_path: Optional[str] = None):
    """Launches a headed Chromium browser for one-time manual login to Reddit and saves session state."""
    settings = get_settings()
    state_path = storage_state_path or settings.reddit.storage_state_path
    abs_state_path = Path(state_path).resolve()
    abs_state_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("VARTALAP - ONE-TIME REDDIT LOGIN CLI")
    print("=" * 60)
    print("Opening headed Chromium browser...")
    print("Please log into your Reddit account manually in the browser window.")
    print("Once logged in successfully, return here and press ENTER to save storage state.")
    print("=" * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://www.reddit.com/login")

        # Wait for user input in console
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, input, "\nPress ENTER here once you have finished logging in... ")

        print("Saving storage state (cookies & localStorage)...")
        await context.storage_state(path=str(abs_state_path))
        print(f"Session saved successfully to: {abs_state_path}")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(run_one_time_login())
