import asyncio
from playwright.async_api import async_playwright, Playwright
from loop import sampling_loop, anthropic_to_invariant
from computer import PlaywrightComputerTool
from anthropic import Anthropic
import json
from invariant_sdk.client import Client as InvariantClient
from dotenv import load_dotenv
load_dotenv()

anthropic_client = Anthropic()
invariant_client = InvariantClient()

async def run(playwright: Playwright):
    browser = await playwright.firefox.launch(headless=False)
    context = await browser.new_context()
    page = await context.new_page()
    await page.goto("https://www.google.com")
    computer_tool = PlaywrightComputerTool(page)
    messages = await sampling_loop(
        model="claude-3-5-sonnet-20241022",
        anthropic_client=anthropic_client,
        messages=[{"role": "user", "content": "How long does it take by car to go from zurich to munich?"}],
        computer_tool=computer_tool,
        page=page,
    )
    json.dump(anthropic_to_invariant(messages), open("messages.json", "w"))
    _ = invariant_client.create_request_and_push_trace(
        messages=[anthropic_to_invariant(messages)],
        dataset="playwright_computer_use_trace"
    )
    await browser.close()
async def main():
    async with async_playwright() as playwright:
        await run(playwright)

asyncio.run(main())
