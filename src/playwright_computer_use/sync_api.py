"""This module contains the PlaywrightToolbox class to be used with an Async Playwright Page."""

from playwright.sync_api import Page
from anthropic.types.beta import BetaToolComputerUse20241022Param, BetaToolParam
from typing import Literal
from PIL import Image
import importlib.resources

import io
import base64
from playwright_computer_use.async_api import (
    ToolError,
    ToolResult,
    ComputerToolOptions,
    Action,
    chunks,
    TYPING_GROUP_SIZE,
    to_playwright_key,
    load_cursor_image,
    _make_api_tool_result,
)


class PlaywrightToolbox:
    """Toolbox for interaction between Claude and Sync Playwright Page."""

    def __init__(self, page: Page, use_cursor: bool = True):
        """Create a new PlaywrightToolbox.

        Args:
            page: The Sync Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
        """
        self.page = page
        self.tools: list[
            PlaywrightComputerTool | PlaywrightSetURLTool | PlaywrightBackTool
        ] = [
            PlaywrightComputerTool(page, use_cursor=use_cursor),
            PlaywrightSetURLTool(page),
            PlaywrightBackTool(page),
        ]

    def to_params(self) -> list[BetaToolParam]:
        """Expose the params of all the tools in the toolbox."""
        return [tool.to_params() for tool in self.tools]

    def run_tool(self, name: str, input: dict, tool_use_id: str):
        """Pick the right tool using `name` and run it."""
        if name not in [tool.name for tool in self.tools]:
            return ToolError(message=f"Unknown tool {name}, only computer use allowed")
        tool = next(tool for tool in self.tools if tool.name == name)
        result = tool(**input)
        return _make_api_tool_result(tool_use_id=tool_use_id, result=result)


class PlaywrightSetURLTool:
    """Tool to navigate to a specific URL."""

    name: Literal["set_url"] = "set_url"

    def __init__(self, page: Page):
        """Create a new PlaywrightSetURLTool.

        Args:
            page: The Sync Playwright page to interact with.
        """
        super().__init__()
        self.page = page

    def to_params(self) -> BetaToolParam:
        """Params describing the tool. Description used by Claude to understand how to this use tool."""
        return BetaToolParam(
            name=self.name,
            description="This tool allows to go directly to a specified URL.",
            input_schema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL of the web page to navigate to.",
                    }
                },
                "required": ["url"],
            },
        )

    def __call__(self, *, url: str):
        """Trigger goto the chosen url."""
        try:
            self.page.goto(url)
            return ToolResult()
        except Exception as e:
            return ToolResult(error=str(e))


class PlaywrightBackTool:
    """Tool to navigate to the previous page."""

    name: Literal["previous_page"] = "previous_page"

    def __init__(self, page: Page):
        """Create a new PlaywrightBackTool.

        Args:
            page: The Sync Playwright page to interact with.
        """
        super().__init__()
        self.page = page

    def to_params(self) -> BetaToolParam:
        """Params describing the tool. Description used by Claude to understand how to this use tool."""
        return BetaToolParam(
            name=self.name,
            description="This tool navigate to the previous page.",
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def __call__(self):
        """Trigger the back button in the browser."""
        try:
            self.page.go_back()
            return ToolResult()
        except Exception as e:
            return ToolResult(error=str(e))


class PlaywrightComputerTool:
    """A tool that allows the agent to interact with Sync Playwright Page."""

    name: Literal["computer"] = "computer"
    api_type: Literal["computer_20241022"] = "computer_20241022"

    @property
    def width(self) -> int:
        """The width of the Playwright page in pixels."""
        return self.page.viewport_size["width"]

    @property
    def height(self) -> int:
        """The height of the Playwright page in pixels."""
        return self.page.viewport_size["height"]

    @property
    def options(self) -> ComputerToolOptions:
        """The options of the tool."""
        return {
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": 0,  # hardcoded
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        """Params describing the tool. Used by Claude to understand this is a computer use tool."""
        return {"name": self.name, "type": self.api_type, **self.options}

    def __init__(self, page: Page, use_cursor: bool = True):
        """Initializes the PlaywrightComputerTool.

        Args:
            page: The Sync Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
        """
        super().__init__()
        self.page = page
        self.use_cursor = use_cursor
        self.mouse_position: tuple[int, int] = (0, 0)

    def __call__(
        self,
        *,
        action: Action,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
        """Run an action. text and coordinate are potential additional parameters."""
        if action in ("mouse_move", "left_click_drag"):
            if coordinate is None:
                raise ToolError(f"coordinate is required for {action}")
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if not isinstance(coordinate, list) or len(coordinate) != 2:
                raise ToolError(f"{coordinate} must be a tuple of length 2")
            if not all(isinstance(i, int) and i >= 0 for i in coordinate):
                raise ToolError(f"{coordinate} must be a tuple of non-negative ints")

            x, y = coordinate

            if action == "mouse_move":
                action = self.page.mouse.move(x, y)
                self.mouse_position = (x, y)
                return ToolResult(output=None, error=None, base64_image=None)
            elif action == "left_click_drag":
                raise NotImplementedError("left_click_drag is not implemented yet")

        if action in ("key", "type"):
            if text is None:
                raise ToolError(f"text is required for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")
            if not isinstance(text, str):
                raise ToolError(output=f"{text} must be a string")

            if action == "key":
                # hande shifts
                self.press_key(text)
                return ToolResult()
            elif action == "type":
                for chunk in chunks(text, TYPING_GROUP_SIZE):
                    self.page.keyboard.type(chunk)
                return self.screenshot()

        if action in (
            "left_click",
            "right_click",
            "double_click",
            "middle_click",
            "screenshot",
            "cursor_position",
        ):
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")

            if action == "screenshot":
                return self.screenshot()
            elif action == "cursor_position":
                return ToolResult(
                    output=f"X={self.mouse_position[0]},Y={self.mouse_position[1]}"
                )
            else:
                click_arg = {
                    "left_click": {"button": "left", "click_count": 1},
                    "right_click": {"button": "right", "click_count": 1},
                    "middle_click": {"button": "middle", "click_count": 1},
                    "double_click": {"button": "left", "click_count": 2, "delay": 100},
                }[action]
                self.page.mouse.click(
                    self.mouse_position[0], self.mouse_position[1], **click_arg
                )
                return ToolResult()

        raise ToolError(f"Invalid action: {action}")

    def screenshot(self) -> ToolResult:
        """Take a screenshot of the current screen and return the base64 encoded image."""
        screenshot = self.page.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        img_small = image.resize((self.width, self.height), Image.LANCZOS)

        if self.use_cursor:
            cursor = load_cursor_image()
            img_small.paste(cursor, self.mouse_position, cursor)
        buffered = io.BytesIO()
        img_small.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode()
        return ToolResult(base64_image=base64_image)

    def press_key(self, key: str):
        """Press a key on the keyboard. Handle + shifts. Eg: Ctrl+Shift+T."""
        shifts = []
        if "+" in key:
            key = key.split("+")[-1]
            shifts += key.split("+")[:-1]
        for shift in shifts:
            self.page.keyboard.down(shift)
        self.page.keyboard.press(to_playwright_key(key))
        for shift in shifts:
            self.page.keyboard.up(shift)
