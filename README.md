# Playwright Computer Use

Easily use the Claude `computer` tool to let an agent interact with a web browser on your machine (playwright).

https://github.com/user-attachments/assets/3d876280-4822-4679-9dd1-689a0f596041

This repo contains the required code to connect a Playwright browser to Claude's computer use capabilities. This enables you to use a browser as a tool for your agent, to interact with web pages, and achieve tasks that require a browser.

**We now also support Claude 3.7!**

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
from playwright_computer_use.sync_api import PlaywrightToolbox #Use sync api when working with sync Playwright page, use async otherwise

tools = PlaywrightToolbox(page=page, use_cursor=True, beta_version="20250124")

# Give Claude access to computer use tool
response = anthropic_client.beta.messages.create(
    ...
    model="claude-3-7-sonnet-20250219",
    tools=tools.to_params(),
    betas=["computer-use-2025-01-24"],
)

# Run computer use tool on playwright
tools.run_tool(**response.content[0].model_dump())
```
For a more in-depth example look at `demo.py`
