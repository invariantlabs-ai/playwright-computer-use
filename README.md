# Playwright-computer-use

This Repo contains a Claude computer use tool that interacts with Playwright.


## Demo
The Demo consists of the computer use agent by Claude, with access to a Playwright instance.
To run the demo:
* Clone the Repo:
```
git clone https://github.com/invariantlabs-ai/playwright-computer-use.git
```
* setup a virtual environment and install requirements
```
python -m venv venv
. venv/bin/activate
pip install .
```
* create a `.env` basing on `.env-example`
* run `python demo.py "How long does it take to travel from Zurich to Milan?"`

## Install
```
pip install git://git@github.com/invariantlabs-ai/playwright-computer-use.git
```
## Use
You can now include `PlaywrightToolbox` as a tool for `Claude`. It would work
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