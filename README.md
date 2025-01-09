# Playwright-computer-use

In `computer.py` is defined a `PlaywrightComputerTool`. Such tool is an Anthropic computer use tool, that is made to interact with an `async` playwright page.

## Demo

An example of an agent using this tool is implemented in `loop.py`.

An example of usage of the agent defined in `loop.py` can be found in `test.py`.

To run it:
* install requirements `pip install -r requirements` (virtual environment recommended)
* create a `.env` basing on `.env-example`
* run `python demo.py "How long does it take to travel from Zurich to Milan?"`
