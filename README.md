# Playwright-computer-use

In `computer.py` is defined a `PlaywrightToolbox`. Such tool is an Anthropic computer use tool, that is made to interact with an `async` playwright page. Plus another couple of tools to use the navigation bar and going back to the previous page.

## Demo

An example of an agent using this tool is implemented in `loop.py`.

An example of usage of the agent defined in `loop.py` can be found in `demo.py`.

To run it:
* setup a virtual environment and install requirements
```ß
python -m venv venv
. venv/bin/activate
pip install -r requirements
```
* create a `.env` basing on `.env-example`
* run `python demo.py "How long does it take to travel from Zurich to Milan?"`
