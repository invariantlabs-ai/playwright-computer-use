"""UI TARS loop."""

import os
import sys
from openai import OpenAI
from src.playwright_ui_tars.sync_api import PlaywrightComputerTool, ActionSignature
from invariant_sdk.client import Client as InvariantClient
from copy import deepcopy
from dotenv import load_dotenv

load_dotenv()
SYSTEM_PROMPT = r"""You are a GUI agent. You are given a task and your action history, with screenshots. You need to perform the next action to complete the task. 

## Output Format
```\nThought: ...
Action: ...\n```

## Action Space

click(start_box='<|box_start|>(x1,y1)<|box_end|>')
left_double(start_box='<|box_start|>(x1,y1)<|box_end|>')
right_single(start_box='<|box_start|>(x1,y1)<|box_end|>')
drag(start_box='<|box_start|>(x1,y1)<|box_end|>', end_box='<|box_start|>(x3,y3)<|box_end|>')
hotkey(key='')
type(content='') #If you want to submit your input, use \"\
\" at the end of `content`.
scroll(start_box='<|box_start|>(x1,y1)<|box_end|>', direction='down or up or right or left')
wait() #Sleep for 5s and take a screenshot to check for any changes.
finished()
call_user() # Submit the task and call the user when the task is unsolvable, or when you need the user's help.


## Note
- Use Chinese in `Thought` part.
- Summarize your next action (with its target element) in one sentence in `Thought` part.

## User Instruction
"""


# function that strips out all but the latest k images from the full chat.
def keep_latest_images(messages, k):
    """Strip old images from a chat, keep only the latest k images."""
    messages = deepcopy(messages)
    images_paths = []
    for i, message in enumerate(messages):
        if "content" in message and message.get("tool_call_id") is None:
            for j, content in enumerate(message["content"]):
                if content["type"] == "image_url":
                    images_paths.append((i, j))
    if len(images_paths) <= k:
        return [m for m in messages if "tool_call_id" not in m]
    images_paths_to_remove = images_paths[:-k]
    images_paths_to_remove.sort(key=lambda x: x[1], reverse=True)
    for i, j in images_paths_to_remove:
        messages[i]["content"].pop(j)

    return [m for m in messages if "tool_call_id" not in m]


def sampling_loop(
    prompt: str,
    client: OpenAI,
    playwright_computer_tool: PlaywrightComputerTool,
):
    """UI TARS sampling loop."""
    messages = []
    screenshot = playwright_computer_tool.screenshot()
    messages.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": SYSTEM_PROMPT + prompt},
                screenshot,
            ],
        }
    )
    go_on = True
    while go_on:
        response = client.chat.completions.create(
            model="ui-tars",
            messages=keep_latest_images(messages, 5),
            frequency_penalty=1,
            max_tokens=128,
        )
        print(response.choices[0].message.content)
        go_on = playwright_computer_tool.parse_and_run_action(
            response.choices[0].message.content
        )
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": response.choices[0].message.content},
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    playwright_computer_tool.screenshot(),
                ],
            }
        )
    return messages


from playwright.sync_api import sync_playwright, Playwright

client = OpenAI(
    api_key="empty",
    base_url="http://127.0.0.1:8000/v1",
)
invariant_client = (
    InvariantClient(api_url="http://127.0.0.1")
    if "INVARIANT_API_KEY" in os.environ
    else None
)


def main(prompt):
    """Run the Agent loop."""
    with sync_playwright() as playwright:
        with playwright.chromium.launch(headless=False) as browser:
            context = browser.new_context()
            page = context.new_page()
            page.set_viewport_size({"width": 1024, "height": 768})
            page.goto("https://www.openstreetmap.org/directions")
            playwright_computer_tool = PlaywrightComputerTool(page=page, verbose=True)
            messages = sampling_loop(
                prompt=prompt,
                client=client,
                playwright_computer_tool=playwright_computer_tool,
            )
    invariant_messages = []
    for message in messages:
        invariant_messages.append(message)
        if message.get("role") == "assistant":
            actions: list[ActionSignature] = []
            for content in message["content"]:
                actions.append(playwright_computer_tool.parse_action(content["text"]))
            if actions:
                invariant_messages.append(
                    {  # append result message
                        "role": "assistant",
                        "tool_call_id": 0,
                        "content": "",
                        "tool_calls": [
                            {
                                "tool_id": "tool_0",
                                "type": "function",
                                "function": action.to_dict(
                                    scale_coords=True, tool=playwright_computer_tool
                                ),
                            }
                            for action in actions
                        ],
                    }
                )
    if invariant_client:
        response = invariant_client.create_request_and_push_trace(
            messages=[invariant_messages],
            dataset="ui-tars",
        )
        url = f"{invariant_client.api_url}/trace/{response.id[0]}"
        print(f"View the trace at {url}")


prompt = sys.argv[1] if len(sys.argv) > 1 else "Click on from."


if __name__ == "__main__":
    main(prompt)
