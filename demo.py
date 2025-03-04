"""Demo of Claude Agent running using Playwright."""

import asyncio
from playwright.async_api import async_playwright, Playwright
from loop import sampling_loop, anthropic_to_invariant
from playwright_computer_use.async_api import PlaywrightToolbox
from anthropic import Anthropic
from invariant_sdk.client import Client as InvariantClient
from dotenv import load_dotenv
import os
import sys


load_dotenv()
MODEL = "claude-3-7-sonnet-20250219"

model_to_beta = {
    "claude-3-7-sonnet-20250219": "20250124",
    "claude-3-5-sonnet-20241022": "20241022",
}

anthropic_client = Anthropic()
invariant_client = InvariantClient() if "INVARIANT_API_KEY" in os.environ else None


async def run(playwright: Playwright, prompt: str):
    """Setup tools and run loop."""
    browser = await playwright.firefox.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    await page.set_viewport_size({"width": 1024, "height": 768})  # Computer-use default
    await page.goto("https://www.google.com")
    playwright_tools = PlaywrightToolbox(
        page, use_cursor=True, beta_version=model_to_beta[MODEL]
    )
    messages = await sampling_loop(
        model=MODEL,
        anthropic_client=anthropic_client,
        messages=[{"role": "user", "content": prompt}],
        tools=playwright_tools,
        page=page,
        verbose=True,
        only_n_most_recent_images=10,
    )
    print(messages[-1]["content"][0]["text"])
    if invariant_client is not None:
        response = invariant_client.create_request_and_push_trace(
            messages=[anthropic_to_invariant(messages)],
            dataset="playwright_computer_use_trace",
        )
        url = f"{invariant_client.api_url}/trace/{response.id[0]}"
        print(f"View the trace at {url}")
    else:
        print(
            "No INVARIANT_API_KEY found. Add it to your .env file to push the trace to Invariant explorer https://explorer.invariantlabs.ai."
        )
    await browser.close()


prompt = sys.argv[1] if len(sys.argv) > 1 else "What is the capital of France?"


async def main():
    """Run the Agent loop."""
    async with async_playwright() as playwright:
        await run(playwright, prompt)


asyncio.run(main())
