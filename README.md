# Playwright Computer Use

Easily use the Claude `computer` tool to let an agent interact with a web browser on your machine (playwright).

This repo contains the required code to connect a Playwright browser to Claude's computer use capabilities. This enables you to use a browser as a tool for your agent, to interact with web pages, and achieve tasks that require a browser.

## Quickstart

Clone the Repo
```
git clone https://github.com/invariantlabs-ai/playwright-computer-use.git
```

Install the dependencies:
```
cd playwright-computer-use
pip install -e .
```

Create a `.env` basing on `.env-example` ([Anthropic Key](https://console.anthropic.com) and an optional [Invariant Key](https://explorer.invariantlabs.ai) for tracing). Then run:

```
python demo.py "How long does it take to travel from Zurich to Milan?"
```

This will spawn an agent on your machine that attempts to achieve whatever task you have in mind in the browser.

## Install As Package

```
pip install git://git@github.com/invariantlabs-ai/playwright-computer-use.git
```

## Using the PlaywrightToolbox as a Library

You can also include the `PlaywrightToolbox` as a tool for `Claude`, to enable the use of a playwright browser in an existing agent.

```python
from computer_sync import PlaywrightToolbox
from anthropic import Anthropic

anthropic_client = Anthropic()

with sync_playwright() as pw:
    browser = pw_mt.firefox.launch(headless=False)
    with browser.new_context() as context:
        page = context.new_page()
        page.set_viewport_size({"width": 1024, "height": 768})  
        tools = PlaywrightToolbox(page=page, use_cursor=True)
        anthropic_client.beta.messages.with_raw_response.create(
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": "Ehi, do you want to take a screenshot?"}],
            model="claude-3-5-sonnet-20241022",
            system=["You are using a browser page to solve your tasks"],
            tools=tools.to_params(),
            betas=["computer-use-2024-10-22"],
        )
        tools
```