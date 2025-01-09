"""
Agentic sampling loop that calls the Anthropic API and local implementation of anthropic-defined computer use tools.
"""
import sys

from collections.abc import Callable
from datetime import datetime
from typing import cast

import httpx
from anthropic import (
    Anthropic,
    AnthropicBedrock,
    AnthropicVertex,
    APIError,
    APIResponseValidationError,
    APIStatusError,
)
from playwright.sync_api import Page
from anthropic.types.beta import (
    BetaCacheControlEphemeralParam,
    BetaContentBlockParam,
    BetaImageBlockParam,
    BetaMessage,
    BetaMessageParam,
    BetaTextBlock,
    BetaTextBlockParam,
    BetaToolResultBlockParam,
    BetaToolUseBlockParam,
)

from computer import PlaywrightToolbox, ToolResult

COMPUTER_USE_BETA_FLAG = "computer-use-2024-10-22"
PROMPT_CACHING_BETA_FLAG = "prompt-caching-2024-07-31"


# This system prompt is optimized for the Docker environment in this repository and
# specific tool combinations enabled.
# We encourage modifying this system prompt to ensure the model has context for the
# environment it is running in, and to provide any additional information that may be
# helpful for the task at hand.
SYSTEM_PROMPT = f"""<SYSTEM_CAPABILITY>
* You are utilising an firefox browser with internet access. The entirity of the task you are given can be solved by navigating from this web page.
* You cannot set the url manually. You can only navigate within the page.
* You can only use one page, and you can't open new tabs.
* When viewing a page it can be helpful to zoom out so that you can see everything on the page.  Either that, or make sure you scroll down to see everything before deciding something isn't available.
* When using your computer function calls, they take a while to run and send back to you.  Where possible/feasible, try to chain multiple of these calls all into one function calls request. At the end always ask for a screenshot, to make sure the state of the page is as you expect.
* The current date is {datetime.today().strftime('%A, %B %-d, %Y')}.
</SYSTEM_CAPABILITY>
"""


async def sampling_loop(
    *,
    model: str,
    anthropic_client: Anthropic | AnthropicVertex | AnthropicBedrock,
    system_prompt: str = SYSTEM_PROMPT,
    messages: list[BetaMessageParam],
    page: Page,
    tools: PlaywrightToolbox,
    output_callback: Callable[[BetaContentBlockParam], None] = None,
    tool_output_callback: Callable[[ToolResult, str], None] = None,
    api_response_callback: Callable[
        [httpx.Request, httpx.Response | object | None, Exception | None], None
    ] = None,
    only_n_most_recent_images: int | None = None,
    max_tokens: int = 4096,
    enable_prompt_caching: bool = True,
    verbose: bool = False,
):
    """
    Agentic sampling loop for the assistant/tool interaction of computer use.
    """
    assert page is not None, "playwright page must be provided"

    system = BetaTextBlockParam(
        type="text",
        text=system_prompt,
    )
    if verbose:
        for message in messages:
            if message["role"] == "user":
                print(f'user > {message["content"]}')
            if message["role"] == "assistant":
                for content_block in message["content"]:
                    if content_block["type"] == "text":
                        print(f'assistant > {content_block["text"]}')
                    if message["role"] == "tool":
                        print(f'tool call > {content_block["name"]} {content_block["input"]}')
    while True:
        enable_prompt_caching = False
        betas = [COMPUTER_USE_BETA_FLAG]
        image_truncation_threshold = only_n_most_recent_images or 0


        if enable_prompt_caching:
            betas.append(PROMPT_CACHING_BETA_FLAG)
            _inject_prompt_caching(messages)
            # Because cached reads are 10% of the price, we don't think it's
            # ever sensible to break the cache by truncating images
            only_n_most_recent_images = 0
            system["cache_control"] = {"type": "ephemeral"}

        if only_n_most_recent_images:
            _maybe_filter_to_n_most_recent_images(
                messages,
                only_n_most_recent_images,
                min_removal_threshold=image_truncation_threshold,
            )

        # Call the API
        # we use raw_response to provide debug information to streamlit. Your
        # implementation may be able call the SDK directly with:
        # `response = client.messages.create(...)` instead.
        try:
            if verbose:
                sys.stdout.write("Calling Model")
                sys.stdout.flush()
            raw_response = anthropic_client.beta.messages.with_raw_response.create(
                max_tokens=max_tokens,
                messages=messages,
                model=model,
                system=[system],
                tools=tools.to_params(),
                betas=betas,
            )
            if verbose:
                sys.stdout.write("\r\033[K")  # Move to the beginning of the line and clear it
                sys.stdout.flush()
        except (APIStatusError, APIResponseValidationError) as e:
            raise e
        except APIError as e:
            api_response_callback(e.request, e.body, e)
            return [{"role": "system", "content": system_prompt}] + messages

        if api_response_callback is not None:
            api_response_callback(
                raw_response.http_response.request, raw_response.http_response, None
            )

        response = raw_response.parse()

        response_params = _response_to_params(response)
        messages.append(
            {
                "role": "assistant",
                "content": response_params,
            }
        )

        tool_result_content: list[BetaToolResultBlockParam] = []
        for content_block in response_params:
            if output_callback is not None:
                output_callback(content_block)
            if content_block["type"] == "tool_use":
                if verbose:
                    print(f'tool call > {content_block["name"]} {content_block["input"]}')
                result = await tools.run_tool(name=content_block["name"], input=content_block["input"])
                tool_result_content.append(
                    _make_api_tool_result(result, content_block["id"])
                )
                if tool_output_callback is not None:
                    tool_output_callback(result, content_block["id"])
            if verbose and content_block["type"] == "text":
                print(f'assistant > {content_block["text"]}')

        if not tool_result_content:
            return [{"role": "system", "content": system_prompt}] + messages

        messages.append({"content": tool_result_content, "role": "user"})


def anthropic_to_invariant(messages: list[dict], keep_empty_tool_response: bool = False) -> list[dict]:
    output = []
    for message in messages:
        if message["role"] == "system":
            output.append({"role": "system", "content": message["content"]})
        if message["role"] == "user":
            if isinstance(message["content"], list):
                for sub_message in message["content"]:
                    assert sub_message["type"] == "tool_result"
                    if sub_message["content"]:
                        assert len(sub_message["content"]) == 1
                        assert sub_message["content"][0]["type"] == "image"
                        output.append({'role': 'tool', 'content': 'local_base64_img: ' + sub_message["content"][0]["source"]["data"], 'tool_id': sub_message["tool_use_id"]})
                    else:
                        if keep_empty_tool_response and any([sub_message[k] for k in sub_message]):
                            output.append({'role': 'tool', 'content': {"is_error": True} if sub_message["is_error"] else {}, 'tool_id': sub_message["tool_use_id"]})
            else:
                output.append({"role": "user", "content": message["content"]})
        if message["role"] == "assistant":
            for sub_message in message["content"]:
                if sub_message["type"] == "text":
                    output.append({"role": "assistant", "content": sub_message.get("text")})
                if sub_message["type"] == "tool_use":
                    output.append({'role': 'assistant', 'content': None, 'tool_calls': [{
                        'tool_id': sub_message.get('id'), 
                        'type': 'function',
                        'function': {'name': sub_message.get('name'),'arguments': sub_message.get('input'),}
                        }]})
    return output


def _maybe_filter_to_n_most_recent_images(
    messages: list[BetaMessageParam],
    images_to_keep: int,
    min_removal_threshold: int,
):
    """
    With the assumption that images are screenshots that are of diminishing value as
    the conversation progresses, remove all but the final `images_to_keep` tool_result
    images in place, with a chunk of min_removal_threshold to reduce the amount we
    break the implicit prompt cache.
    """
    if images_to_keep is None:
        return messages

    tool_result_blocks = cast(
        list[BetaToolResultBlockParam],
        [
            item
            for message in messages
            for item in (
                message["content"] if isinstance(message["content"], list) else []
            )
            if isinstance(item, dict) and item.get("type") == "tool_result"
        ],
    )

    total_images = sum(
        1
        for tool_result in tool_result_blocks
        for content in tool_result.get("content", [])
        if isinstance(content, dict) and content.get("type") == "image"
    )

    images_to_remove = total_images - images_to_keep
    # for better cache behavior, we want to remove in chunks
    images_to_remove -= images_to_remove % min_removal_threshold

    for tool_result in tool_result_blocks:
        if isinstance(tool_result.get("content"), list):
            new_content = []
            for content in tool_result.get("content", []):
                if isinstance(content, dict) and content.get("type") == "image":
                    if images_to_remove > 0:
                        images_to_remove -= 1
                        continue
                new_content.append(content)
            tool_result["content"] = new_content


def _response_to_params(
    response: BetaMessage,
) -> list[BetaTextBlockParam | BetaToolUseBlockParam]:
    res: list[BetaTextBlockParam | BetaToolUseBlockParam] = []
    for block in response.content:
        if isinstance(block, BetaTextBlock):
            res.append({"type": "text", "text": block.text})
        else:
            res.append(cast(BetaToolUseBlockParam, block.model_dump()))
    return res


def _inject_prompt_caching(
    messages: list[BetaMessageParam],
):
    """
    Set cache breakpoints for the 3 most recent turns
    one cache breakpoint is left for tools/system prompt, to be shared across sessions
    """

    breakpoints_remaining = 3
    for message in reversed(messages):
        if message["role"] == "user" and isinstance(
            content := message["content"], list
        ):
            if breakpoints_remaining:
                breakpoints_remaining -= 1
                content[-1]["cache_control"] = BetaCacheControlEphemeralParam(
                    {"type": "ephemeral"}
                )
            else:
                content[-1].pop("cache_control", None)
                # we'll only every have one extra turn per loop
                break


def _make_api_tool_result(
    result: ToolResult, tool_use_id: str
) -> BetaToolResultBlockParam:
    """Convert an agent ToolResult to an API ToolResultBlockParam."""
    tool_result_content: list[BetaTextBlockParam | BetaImageBlockParam] | str = []
    is_error = False
    if result.error:
        is_error = True
        tool_result_content = _maybe_prepend_system_tool_result(result, result.error)
    else:
        if result.output:
            tool_result_content.append(
                {
                    "type": "text",
                    "text": _maybe_prepend_system_tool_result(result, result.output),
                }
            )
        if result.base64_image:
            tool_result_content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": result.base64_image,
                    },
                }
            )
    return {
        "type": "tool_result",
        "content": tool_result_content,
        "tool_use_id": tool_use_id,
        "is_error": is_error,
    }


def _maybe_prepend_system_tool_result(result: ToolResult, result_text: str):
    if result.system:
        result_text = f"<system>{result.system}</system>\n{result_text}"
    return result_text
