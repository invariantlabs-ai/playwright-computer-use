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
You can now include `PlaywrightToolbox` as a tool for `Claude`. It would work as any other tool.
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
