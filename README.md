# Playwright Computer Use

Easily use the Claude `computer` tool to let an agent interact with a web browser on your machine (playwright).

This repo contains the required code to connect a Playwright browser to Claude's computer use capabilities. This enables you to use a browser as a tool for your agent, to interact with web pages, and achieve tasks that require a browser.

## Quickstart

Clone the Repo
```
git clone https://github.com/invariantlabs-ai/playwright-computer-use.git
```

Setup a virtual environment and install the requirements
```
python -m venv venv
. venv/bin/activate
pip install .
```

Create a `.env` basing on `.env-example` ([Anthropic Key](https://console.anthropic.com) and an optional [Invariant Key](https://explorer.invariantlabs.ai) for tracing)

Then run

```
python demo.py "How long does it take to travel from Zurich to Milan?"
```

This will spawn an agent on your machine, that attempts to achieve whatever task you have in mind in the browser.

## Install As Package

```
pip install git://git@github.com/invariantlabs-ai/playwright-computer-use.git
```

## Using the PlaywrightToolbox as a Library

You can also include the `PlaywrightToolbox` as a tool for `Claude`, to enable the use of a playwright browser in an existing agent.

```python
tools = tools = PlaywrightToolbox(page=page, use_cursor=True)

# Give Claude access to computer use tool
response = anthropic_client.beta.messages.create(
    ...
    tools=tools.to_params(),
    betas=["computer-use-2024-10-22"],
)

# Run computer use tool on playwright
tools.run_tool(**response.content[0].model_dump())
```
For a more in-depth example look at `demo.py`
