"""This module contains the PlaywrightToolbox class to be used with an Async Playwright Page."""

from playwright.sync_api import Page
from anthropic.types.beta import (
    BetaToolComputerUse20241022Param,
    BetaToolParam,
    BetaToolComputerUse20250124Param,
)
from typing import Literal, get_args, cast, Type
from PIL import Image
import importlib.resources
from time import sleep
import io
import base64
from playwright_computer_use.async_api import (
    ToolError,
    ToolResult,
    ComputerToolOptions,
    Action_20250124,
    Action_20241022,
    ScrollDirection,
    chunks,
    TYPING_GROUP_SIZE,
    SCROLL_MULTIPLIER_FACTOR,
    to_playwright_key,
    load_cursor_image,
    _make_api_tool_result,
)


class PlaywrightToolbox:
    """Toolbox for interaction between Claude and Async Playwright Page."""

    def __init__(
        self,
        page: Page,
        use_cursor: bool = True,
        screenshot_wait_until: Literal["load", "domcontentloaded", "networkidle"]
        | None = None,
        beta_version: Literal["20241022", "20250124"] = "20250124",
    ):
        """Create a new PlaywrightToolbox.

        Args:
            page: The Async Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
            screenshot_wait_until: Optional, wait until the page is in a specific state before taking a screenshot. Default does not wait
            beta_version: The version of the beta to use. Default is the latest version (Claude3.7)
        """
        self.page = page
        self.beta_version = beta_version
        computer_tool_map: dict[str, Type[BasePlaywrightComputerTool]] = {
            "20241022": PlaywrightComputerTool20241022,
            "20250124": PlaywrightComputerTool20250124,
        }
        ComputerTool = computer_tool_map[beta_version]
        self.tools: list[
            BasePlaywrightComputerTool | PlaywrightSetURLTool | PlaywrightBackTool
        ] = [
            ComputerTool(
                page, use_cursor=use_cursor, screenshot_wait_until=screenshot_wait_until
            ),
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


class BasePlaywrightComputerTool:
    """A tool that allows the agent to interact with Sync Playwright Page."""

    name: Literal["computer"] = "computer"

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

    def to_params(self):
        """Params describing the tool. Used by Claude to understand this is a computer use tool."""
        raise NotImplementedError("to_params must be implemented in the subclass")

    def __init__(
        self,
        page: Page,
        use_cursor: bool = True,
        screenshot_wait_until: Literal["load", "domcontentloaded", "networkidle"]
        | None = None,
    ):
        """Initializes the PlaywrightComputerTool.

        Args:
            page: The Sync Playwright page to interact with.
            use_cursor: Whether to display the cursor in the screenshots or not.
            screenshot_wait_until: Optional, wait until the page is in a specific state before taking a screenshot. Default does not wait
        """
        super().__init__()
        self.page = page
        self.use_cursor = use_cursor
        self.mouse_position: tuple[int, int] = (0, 0)
        self.screenshot_wait_until = screenshot_wait_until

    def __call__(
        self,
        *,
        action: Action_20241022,
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
        if self.screenshot_wait_until is not None:
            self.page.wait_for_load_state(self.screenshot_wait_until)
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
            shifts += key.split("+")[:-1]
            key = key.split("+")[-1]
        for shift in shifts:
            self.page.keyboard.down(shift)
        self.page.keyboard.press(to_playwright_key(key))
        for shift in shifts:
            self.page.keyboard.up(shift)


class PlaywrightComputerTool20241022(BasePlaywrightComputerTool):
    """Tool to interact with the computer using Playwright (Beta 22/10/2024)."""

    api_type: Literal["computer_20241022"] = "computer_20241022"

    def to_params(self) -> BetaToolComputerUse20241022Param:
        """Params describing the tool. Used by Claude to understand this is a computer use tool."""
        return {"name": self.name, "type": self.api_type, **self.options}


class PlaywrightComputerTool20250124(BasePlaywrightComputerTool):
    """Tool to interact with the computer using Playwright (Beta 24/01/2025)."""

    api_type: Literal["computer_20250124"] = "computer_20250124"

    def to_params(self) -> BetaToolComputerUse20250124Param:
        """Params describing the tool. Used by Claude to understand this is a computer use tool."""
        return {"name": self.name, "type": self.api_type, **self.options}

    def __call__(
        self,
        *,
        action: Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        **kwargs,
    ):
        """Run an action. text, coordinate, scroll_directions, scroll_amount, duration, key are potential additional parameters."""
        if action in ("left_mouse_down", "left_mouse_up"):
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action=}.")
            self.page.mouse.down() if action == "left_mouse_down" else self.page.mouse.up()
            return ToolResult()
        if action == "scroll":
            if scroll_direction is None or scroll_direction not in get_args(
                ScrollDirection
            ):
                raise ToolError(
                    f"{scroll_direction=} must be 'up', 'down', 'left', or 'right'"
                )
            if not isinstance(scroll_amount, int) or scroll_amount < 0:
                raise ToolError(f"{scroll_amount=} must be a non-negative int")
            if coordinate is not None:
                x, y = coordinate
                self.page.mouse.move(x, y)
                self.mouse_position = (x, y)
            scroll_amount *= SCROLL_MULTIPLIER_FACTOR
            scroll_params = {
                "up": {"delta_y": -scroll_amount, "delta_x": 0},
                "down": {"delta_y": scroll_amount, "delta_x": 0},
                "left": {"delta_y": 0, "delta_x": scroll_amount},
                "right": {"delta_y": 0, "delta_x": -scroll_amount},
            }[scroll_direction]

            self.page.mouse.wheel(**scroll_params)
            return ToolResult()

        if action in ("hold_key", "wait"):
            if duration is None or not isinstance(duration, (int, float)):
                raise ToolError(f"{duration=} must be a number")
            if duration < 0:
                raise ToolError(f"{duration=} must be non-negative")
            if duration > 100:
                raise ToolError(f"{duration=} is too long.")

            if action == "hold_key":
                if text is None:
                    raise ToolError(f"text is required for {action}")
                self.page.keyboard.press(to_playwright_key(text), delay=duration)
                return ToolResult()

            if action == "wait":
                sleep(duration)
                return self.screenshot()

        if action in (
            "left_click",
            "right_click",
            "double_click",
            "triple_click",
            "middle_click",
        ):
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if coordinate is not None:
                x, y = coordinate
                self.page.mouse.move(x, y)
                self.mouse_position = (x, y)

            click_arg = {
                "left_click": {"button": "left", "click_count": 1},
                "right_click": {"button": "right", "click_count": 1},
                "middle_click": {"button": "middle", "click_count": 1},
                "double_click": {"button": "left", "click_count": 2, "delay": 10},
                "double_click": {"button": "left", "click_count": 3, "delay": 10},
            }[action]
            if key:
                self.page.keyboard.down(to_playwright_key(key))
            self.page.mouse.click(
                self.mouse_position[0], self.mouse_position[1], **click_arg
            )
            if key:
                self.page.keyboard.up(to_playwright_key(key))

            return ToolResult()

        action = cast(Action_20241022, action)
        return super().__call__(
            action=action, text=text, coordinate=coordinate, key=key, **kwargs
        )
