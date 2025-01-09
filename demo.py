import asyncio
from playwright.async_api import async_playwright, Playwright
from loop import sampling_loop, anthropic_to_invariant
from computer import PlaywrightToolbox
from anthropic import Anthropic
import json
from invariant_sdk.client import Client as InvariantClient
from dotenv import load_dotenv
import sys
load_dotenv()

anthropic_client = Anthropic()
invariant_client = InvariantClient()

async def run(playwright: Playwright, prompt: str):
    browser = await playwright.firefox.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto("https://www.google.com")
    playwright_tools = PlaywrightToolbox(page)
    messages = await sampling_loop(
        model="claude-3-5-sonnet-20241022",
        anthropic_client=anthropic_client,
        messages=[{"role": "user", "content": prompt}],
        tools=playwright_tools,
        page=page,
        verbose=True
    )
    print(messages[-1]["content"][0]["text"])
    response = invariant_client.create_request_and_push_trace(
        messages=[anthropic_to_invariant(messages)],
        dataset="playwright_computer_use_trace"
    )
    url = f"{invariant_client.api_url}/trace/{response.id[0]}"
    print(f"View the trace at {url}")
    await browser.close()

prompt = sys.argv[1]
async def main():
    async with async_playwright() as playwright:
        await run(playwright, prompt)


asyncio.run(main())
