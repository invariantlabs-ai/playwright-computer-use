"""This module contains the PlaywrightToolbox class to be used with an Async Playwright Page."""

import importlib.resources
import base64
from enum import StrEnum
from typing import Literal, TypedDict
from playwright.async_api import Page
from PIL import Image
import io
from anthropic.types.beta import (
    BetaToolComputerUse20241022Param,
    BetaToolParam,
    BetaToolResultBlockParam,
    BetaTextBlockParam,
    BetaImageBlockParam,
)
from dataclasses import dataclass

TYPING_GROUP_SIZE = 50

Action = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]


class ComputerToolOptions(TypedDict):
    """Options for the computer tool."""

    display_height_px: int
    display_width_px: int
    display_number: int | None


def chunks(s: str, chunk_size: int) -> list[str]:
    """Split a string into chunks of a specific size."""
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None


class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        """Create a new ToolError."""
        self.message = message


class PlaywrightToolbox:
    """Toolbox for interaction between Claude and Async Playwright Page."""

    def __init__(self, page: Page, use_cursor: bool = True):
        """Create a new PlaywrightToolbox.

        Args:
            page: The Async Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
        """
        self.page = page
        self.tools: list[
            PlaywrightComputerTool | PlaywrightSetURLTool | PlaywrightBackTool
        ] = [
            PlaywrightComputerTool(page, use_cursor=use_cursor),
            PlaywrightSetURLTool(page),
            PlaywrightBackTool(page),
            LogTool(),
        ]

    def to_params(self) -> list[BetaToolParam]:
        """Expose the params of all the tools in the toolbox."""
        return [tool.to_params() for tool in self.tools]

    async def run_tool(
        self, name: str, input: dict, tool_use_id: str
    ) -> BetaToolResultBlockParam:
        """Pick the right tool using `name` and run it."""
        if name not in [tool.name for tool in self.tools]:
            return ToolError(message=f"Unknown tool {name}, only computer use allowed")
        tool = next(tool for tool in self.tools if tool.name == name)
        result = await tool(**input)
        return _make_api_tool_result(tool_use_id=tool_use_id, result=result)


class PlaywrightSetURLTool:
    """Tool to navigate to a specific URL."""

    name: Literal["set_url"] = "set_url"

    def __init__(self, page: Page):
        """Create a new PlaywrightSetURLTool.

        Args:
            page: The Async Playwright page to interact with.
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

    async def __call__(self, *, url: str):
        """Trigger goto the chosen url."""
        try:
            await self.page.goto(url)
            return ToolResult()
        except Exception as e:
            return ToolResult(error=str(e))


class PlaywrightBackTool:
    """Tool to navigate to the previous page."""

    name: Literal["previous_page"] = "previous_page"

    def __init__(self, page: Page):
        """Create a new PlaywrightBackTool.

        Args:
            page: The Async Playwright page to interact with.
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

    async def __call__(self):
        """Trigger the back button in the browser."""
        try:
            await self.page.go_back()
            return ToolResult()
        except Exception as e:
            return ToolResult(error=str(e))


# tool like the above, but it only prints a [LOG] message, and does not interact with the playwright page.
# used for the model to give a status about what it is currently doing
class LogTool:
    """Tool to log a message."""

    name: Literal["log"] = "log"

    def __init__(self):
        """Create a new LogTool."""
        super().__init__()

    def to_params(self) -> BetaToolParam:
        """Params describing the tool. Description used by Claude to understand how to this use tool."""
        return BetaToolParam(
            name=self.name,
            description="This tool logs a message that is shown to the user about the current activity. Always use this tool before any action sequence. Before pressing any button or making a change beyond navigation, e.g. write a message like 'Clicking the Buy button'.",
            input_schema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to log.",
                    }
                },
                "required": ["message"],
            },
        )

    async def __call__(self, *, message: str):
        """Print the message."""
        print(f"[LOG] {message}")
        return ToolResult()


class PlaywrightComputerTool:
    """A tool that allows the agent to interact with Async Playwright Page."""

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
            "display_number": 1,  # hardcoded
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        """Params describing the tool. Used by Claude to understand this is a computer use tool."""
        return {"name": self.name, "type": self.api_type, **self.options}

    def __init__(
        self,
        page: Page,
        use_cursor: bool = True,
        screenshot_wait_until: Literal["load", "domcontentloaded", "networkidle"]
        | None = None,
    ):
        """Initializes the PlaywrightComputerTool.

        Args:
            page: The Async Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
            screenshot_wait_until: Optional, wait until the page is in a specific state before taking a screenshot. Default does not wait
        """
        super().__init__()
        self.page = page
        self.use_cursor = use_cursor
        self.mouse_position: tuple[int, int] = (0, 0)
        self.screenshot_wait_until = screenshot_wait_until

    async def __call__(
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
                action = await self.page.mouse.move(x, y)
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
                await self.press_key(text)
                return ToolResult()
            elif action == "type":
                for chunk in chunks(text, TYPING_GROUP_SIZE):
                    await self.page.keyboard.type(chunk)
                return await self.screenshot()

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
                return await self.screenshot()
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
                await self.page.mouse.click(
                    self.mouse_position[0], self.mouse_position[1], **click_arg
                )
                return ToolResult()

        raise ToolError(f"Invalid action: {action}")

    async def screenshot(self) -> ToolResult:
        """Take a screenshot of the current screen and return the base64 encoded image."""
        if self.screenshot_wait_until is not None:
            await self.page.wait_for_load_state(self.screenshot_wait_until)
        await self.page.wait_for_load_state()
        screenshot = await self.page.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        img_small = image.resize((self.width, self.height), Image.LANCZOS)
        if self.use_cursor:
            cursor = load_cursor_image()
            img_small.paste(cursor, self.mouse_position, cursor)
        buffered = io.BytesIO()
        img_small.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode()
        return ToolResult(base64_image=base64_image)

    async def press_key(self, key: str):
        """Press a key on the keyboard. Handle + shifts. Eg: Ctrl+Shift+T."""
        shifts = []
        if "+" in key:
            key = key.split("+")[-1]
            shifts += key.split("+")[:-1]
        for shift in shifts:
            await self.page.keyboard.down(shift)

        prkey = to_playwright_key(key)
        # for PageDown and PageUp scroll in the page
        if prkey == "PageDown":
            await self.page.mouse.wheel(
                delta_y=0.5 * self.page.viewport_size["height"], delta_x=0
            )
        elif prkey == "PageUp":
            await self.page.mouse.wheel(
                delta_y=-0.5 * self.page.viewport_size["height"], delta_x=0
            )
        else:
            await self.page.keyboard.press(prkey)

        for shift in shifts:
            await self.page.keyboard.up(shift)


def to_playwright_key(key: str) -> str:
    """Convert a key to the Playwright key format."""
    valid_keys = (
        ["F{i}" for i in range(1, 13)]
        + ["Digit{i}" for i in range(10)]
        + ["Key{i}" for i in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        + [
            "Backquote",
            "Minus",
            "Equal",
            "Backslash",
            "Backspace",
            "Tab",
            "Delete",
            "Escape",
            "ArrowDown",
            "End",
            "Enter",
            "Home",
            "Insert",
            "PageDown",
            "PageUp",
            "ArrowRight",
            "ArrowUp",
        ]
    )
    if key in valid_keys:
        return key
    if key == "Return":
        return "Enter"
    if key == "Page_Down":
        return "PageDown"
    if key == "Page_Up":
        return "PageUp"
    if key == "Left":
        return "ArrowLeft"
    if key == "Right":
        return "ArrowRight"
    if key == "Up":
        return "ArrowUp"
    if key == "Down":
        return "ArrowDown"
    if key == "BackSpace":
        return "Backspace"
    if key == "alt":
        return "Alt"
    print(f"Key {key} is not properly mapped into playwright")
    return key


def load_cursor_image():
    """Access the cursor.png file in the assets directory."""
    with importlib.resources.open_binary(
        "playwright_computer_use.assets", "cursor.png"
    ) as img_file:
        image = Image.open(img_file)
        image.load()  # Ensure the image is fully loaded into memory
    return image


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    if result.error:
        return BetaToolResultBlockParam(
            tool_use_id=tool_use_id,
            is_error=True,
            content=result.error,
            type="tool_result",
        )
    else:
        tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] = []
        if result.output:
            tool_result_content.append(
                BetaTextBlockParam(
                    type="text",
                    text=result.output,
                )
            )
        if result.base64_image:
            tool_result_content.append(
                BetaImageBlockParam(
                    type="image",
                    source={
                        "type": "base64",
                        "media_type": "image/png",
                        "data": result.base64_image,
                    },
                )
            )
        return BetaToolResultBlockParam(
            tool_use_id=tool_use_id,
            is_error=False,
            content=tool_result_content,
            type="tool_result",
        )
