"""Playwright UI-TARS Sync API."""

from __future__ import annotations
from typing import Literal, Any
from playwright.sync_api import Page
import inspect
import ast
import logging
import io
from playwright_computer_use.async_api import load_cursor_image
from PIL import Image
import base64
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class PlaywrightComputerTool:
    """A tool that allows the UI-TARS to interact with Sync Playwright Page."""

    @property
    def width(self) -> int:
        """The width of the Playwright page in pixels."""
        return self.page.viewport_size["width"]

    @property
    def height(self) -> int:
        """The height of the Playwright page in pixels."""
        return self.page.viewport_size["height"]

    def _relative_to_absolute_coords(self, coords: tuple[int, int]) -> tuple[int, int]:
        """Converts relative coordinates to absolute coordinates."""
        return (coords[0] * self.width // 1000, coords[1] * self.height // 1000)

    def __init__(self, page: Page, verbose: bool = False, use_cursor: bool = True):
        """Initializes the PlaywrightComputerTool with a Playwright Page object."""
        self.page = page
        self.verbose = verbose
        self.use_cursor = use_cursor
        self.mouse_position: tuple[int, int] = (0, 0)

    def action_click(self, start_box: tuple[int, int]) -> Literal[True]:
        """Click action."""
        if self.verbose:
            logger.info(f"Clicking on {start_box}")
        start_box = self._relative_to_absolute_coords(start_box)
        self.mouse_position = start_box
        self.page.mouse.click(*start_box)
        return True

    def action_left_double(self, start_box: tuple[int, int]) -> Literal[True]:
        """Double click action."""
        if self.verbose:
            logger.info(f"Double clicking on {start_box}")
        start_box = self._relative_to_absolute_coords(start_box)
        self.mouse_position = start_box
        self.page.mouse.dblclick(*start_box)
        return True

    def action_right_single(self, start_box: tuple[int, int]) -> Literal[True]:
        """Right click action."""
        if self.verbose:
            logger.info(f"Right clicking on {start_box}")
        start_box = self._relative_to_absolute_coords(start_box)
        self.mouse_position = start_box
        self.page.mouse.click(*start_box, button="right")
        return True

    def action_drag(
        self, start_box: tuple[int, int], end_box: tuple[int, int]
    ) -> Literal[True]:
        """Drag action."""
        if self.verbose:
            logger.info(f"Dragging from {start_box} to {end_box}")
        start_box = self._relative_to_absolute_coords(start_box)
        end_box = self._relative_to_absolute_coords(end_box)
        self.mouse_position = end_box
        self.page.drag_and_drop(source=start_box, target=end_box)
        return True

    def action_hotkey(self, key: str) -> Literal[True]:
        """Hotkey action."""
        if self.verbose:
            logger.info(f"Pressing hotkey {key}")
        key = to_playwright_key(key)
        self.page.keyboard.press(key)
        return True

    def action_type(self, content: str) -> Literal[True]:
        """Type action."""
        if self.verbose:
            logger.info(f"Typing {content}")
        self.page.keyboard.type(content)
        return True

    def action_scroll(
        self,
        direction: Literal["down", "up", "right", "left"],
        start_box: tuple[int, int] | None = None,
    ) -> Literal[True]:
        """Scroll action."""
        if self.verbose:
            logger.info(f"Scrolling {direction} from {start_box}")
        deltaX, deltaY = 0, 0
        if direction == "down":
            deltaY = 100
        elif direction == "up":
            deltaY = -100
        elif direction == "right":
            deltaX = 100
        elif direction == "left":
            deltaX = -100
        if start_box is not None:
            start_box = self._relative_to_absolute_coords(start_box)
            self.mouse_position = start_box
        self.page.mouse.move(*start_box)
        self.page.mouse.wheel(delta_x=deltaX, delta_y=deltaY)
        return True

    def action_wait(self) -> Literal[True]:
        """Wait action."""
        if self.verbose:
            logger.info("Waiting for 5s")
        self.page.wait_for_timeout(5000)
        return True

    def action_finished(self) -> Literal[False]:
        """Finished action. go_on = False."""
        if self.verbose:
            logger.info("Finished")
        return False

    def action_call_user(self) -> Literal[False]:
        """Call user action. go_on = False."""
        if self.verbose:
            logger.info("Calling user function")
        return False

    def press_key(self, key: str):
        """Press a key on the keyboard. Handle + shifts. Eg: Ctrl+Shift+T."""
        shifts = []
        if " " in key:
            shifts += key.split(" ")[:-1]
            key = key.split(" ")[-1]
        for shift in shifts:
            self.page.keyboard.down(shift)
        self.page.keyboard.press(to_playwright_key(key))
        for shift in shifts:
            self.page.keyboard.up(shift)

    def _screenshot(self) -> str:
        screenshot = self.page.screenshot()
        image = Image.open(io.BytesIO(screenshot))
        img_small = image.resize((self.width, self.height), Image.LANCZOS)

        if self.use_cursor:
            cursor = load_cursor_image()
            img_small.paste(cursor, self.mouse_position, cursor)
        buffered = io.BytesIO()
        img_small.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    def screenshot(self) -> dict[str, Any]:
        """Take a screenshot of the current page. Return it as a OpenAI message."""
        return {
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{self._screenshot()}"},
        }

    def parse_action(self, model_message: str) -> ActionSignature | None:
        """Function to parse the model action message."""
        # finding the line with action
        lines = model_message.split("\n")
        for line in lines:
            if line.startswith("Action"):
                action_line = line
                break
        else:
            logger.warning("No action found in the message.")
            return None

        # parsing
        action_title = action_line.split(": ")[0]
        assert action_title == "Action"
        action_call = action_line.split(": ")[1]
        parsed_action = ast.parse(action_call)
        fn_name = parsed_action.body[0].value.func.id  # type: ignore
        fn_args = parsed_action.body[0].value.args  # type: ignore
        fn_kwargs = parsed_action.body[0].value.keywords  # type: ignore

        fn_args = [arg.value for arg in fn_args]  # type: ignore
        fn_kwargs = {kw.arg: kw.value.value for kw in fn_kwargs}  # type: ignore
        return ActionSignature(
            name=fn_name, args=fn_args, kwargs=parse_kwargs(fn_kwargs)
        )

    def run_action(self, action: ActionSignature) -> bool:
        """Function to run the model action message."""
        action_func = getattr(self, f"action_{action.name}")
        # running the action
        return action_func(*action.args, **action.kwargs)

    def parse_and_run_action(self, model_message: str) -> bool:
        """Function to parse the model action message and execute."""
        action = self.parse_action(model_message)
        if action is None:
            return False
        return self.run_action(action)


def parse_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Parse the kwargs to the correct type."""
    nkwargs = {}
    for k in kwargs:
        if k in ["start_box", "end_box"]:
            nkwargs[k] = ast.literal_eval(kwargs[k])
        else:
            nkwargs[k] = kwargs[k]
    return nkwargs


@dataclass
class ActionSignature:
    """Dataclass to store function signature."""

    name: str
    args: list[str]
    kwargs: dict[str, Any]

    def to_dict(
        self, scale_coords: bool = False, tool: PlaywrightComputerTool | None = None
    ) -> dict[str, Any]:
        """Serialize function signature to a dictionary."""
        if scale_coords:
            if tool is None:
                raise ValueError("tool argument is required when scale_coords is True.")
            scaled_kwargs = {}
            for k in self.kwargs:
                if k in ["start_box", "end_box"]:
                    scaled_kwargs[k] = tool._relative_to_absolute_coords(self.kwargs[k])
                else:
                    scaled_kwargs[k] = self.kwargs[k]
        else:
            scaled_kwargs = self.kwargs
        return {
            "name": self.name,
            "arguments": {f"arg{i}": arg for i, arg in enumerate(self.args)}
            | scaled_kwargs,
        }


def to_playwright_key(key: str) -> str:
    """Convert a key to the Playwright key format."""
    valid_keys = (
        ["F{i}" for i in range(1, 13)]
        + ["Digit{i}" for i in range(10)]
        + ["Key{i}" for i in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        + [i for i in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
        + [i.lower() for i in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
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
    if key == "enter":
        return "Enter"
    if key == "pagedown":
        return "PageDown"
    if key == "pageup":
        return "PageUp"
    if key == "backspace":
        return "Backspace"
    if key == "ctrl":
        return "Ctrl"
    if key == "arrowdown":
        return "ArrowDown"
    if key == "arrowup":
        return "ArrowUp"
    print(f"Key {key} is not properly mapped into playwright")
    return key
