import base64
from enum import StrEnum
from typing import Literal, TypedDict
from playwright.async_api import Page
from PIL import Image
import io
from anthropic.types.beta import BetaToolComputerUse20241022Param
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


class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: int | None


def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]


@dataclass(kw_only=True, frozen=True)
class ToolResult:
    """Represents the result of a tool execution."""

    output: str | None = None
    error: str | None = None
    base64_image: str | None = None
    system: str | None = None



class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message



class PlaywrightComputerTool:
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of the current computer.
    The tool parameters are defined by Anthropic and are not editable.
    """

    name: Literal["computer"] = "computer"
    api_type: Literal["computer_20241022"] = "computer_20241022"

    @property
    def width(self) -> int:
        return self.page.viewport_size["width"]

    @property
    def height(self) -> int:
        return self.page.viewport_size["height"]

    @property
    def options(self) -> ComputerToolOptions:
        return {
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": 0, # hardcoded
        }


    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {"name": self.name, "type": self.api_type, **self.options}

    def __init__(self, page: Page):
        super().__init__()
        self.page = page

    async def __call__(
        self,
        *,
        action: Action,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
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
                return ToolResult(output=f"X={self.mouse_position[0]},Y={self.mouse_position[1]}")
            else:
                click_arg = {
                    "left_click": {"button": "left", "click_count": 1},
                    "right_click": {"button": "right", "click_count": 1},
                    "middle_click": {"button": "middle", "click_count": 1},
                    "double_click":{"button": "left", "click_count": 2, "delay": 100},
                }[action]
                await self.page.mouse.click(self.mouse_position[0], self.mouse_position[1], **click_arg)
                return ToolResult()

        raise ToolError(f"Invalid action: {action}")

    async def screenshot(self) -> ToolResult:
        """Take a screenshot of the current screen and return the base64 encoded image."""
        screenshot = await self.page.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        img_small = image.resize((self.width, self.height), Image.LANCZOS)
        buffered = io.BytesIO()
        img_small.save(buffered, format="PNG")
        base64_image = base64.b64encode(buffered.getvalue()).decode()
        return ToolResult(base64_image=base64_image)

    async def press_key(self, key: str):
        """Press a key on the keyboard. Handle + shifts. Eg: Ctrl+Shift+T"""
        shifts = []
        if "+" in key:
            key = key.split("+")[-1]
            shifts += key.split("+")[:-1]
        for shift in shifts:
            await self.page.keyboard.down(shift)
        await self.page.keyboard.press(to_playwright_key(key))
        for shift in shifts:
            await self.page.keyboard.up(shift)

def to_playwright_key(key: str) -> str:
    """Convert a key to the Playwright key format."""
    valid_keys = ["F{i}" for i in range(1, 13)] + ["Digit{i}" for i in range(10)] + ["Key{i}" for i in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"] + [
        "Backquote", "Minus", "Equal", "Backslash", "Backspace", "Tab", "Delete", "Escape", "ArrowDown", "End", "Enter", "Home", "Insert", "PageDown", "PageUp", "ArrowRight", "ArrowUp"
    ]
    if key in valid_keys:
        return key
    if key == "Return":
        return "Enter"
    if key == "Page_Down":
        return "PageDown"
    if key == "Page_Up":
        return "PageUp"
    print(f"Key {key} is not properly mapped into playwright")
    return key
