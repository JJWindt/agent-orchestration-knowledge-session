import json
import inspect
from dataclasses import dataclass
from typing import List, Callable, Optional

from pydantic import BaseModel
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from langchain_core.tools import StructuredTool


@dataclass
class Agent:
    name: str
    instructions: str
    tools: List[Callable]
    llm: BaseChatModel


class Response(BaseModel):
    agent: Optional[Agent]
    messages: List


def _to_langchain_tool(func: Callable) -> StructuredTool:
    return StructuredTool.from_function(
        func=func,
        name=func.__name__,
        description=(func.__doc__ or "").strip(),
    )


def run_full_turn(agent: Agent, messages: list) -> Response:
    """Run one user turn: call the LLM, execute any tool calls, handle agent transfers.

    Returns a Response with the (possibly updated) agent and only the new messages
    produced during this turn.
    """
    current_agent = agent
    messages = messages.copy()
    num_init_messages = len(messages)

    while True:
        langchain_tools = [_to_langchain_tool(t) for t in current_agent.tools]
        full_messages = [SystemMessage(content=current_agent.instructions)] + messages

        llm = current_agent.llm
        response = (
            llm.bind_tools(langchain_tools).invoke(full_messages)
            if langchain_tools
            else llm.invoke(full_messages)
        )

        message = AIMessage(
            content=response.content or "",
            tool_calls=response.tool_calls if response.tool_calls else [],
        )
        messages.append(message)

        if response.content:
            print(f"{current_agent.name}: {response.content}")

        if not response.tool_calls:
            break

        for tool_call in response.tool_calls:
            tool_func = next(
                (t for t in current_agent.tools if t.__name__ == tool_call["name"]),
                None,
            )

            if tool_func is None:
                result_content = f"Tool '{tool_call['name']}' not found."
            else:
                try:
                    result = tool_func(**tool_call["args"])

                    if isinstance(result, Agent):
                        current_agent = result
                        result_content = f"Transferred to {current_agent.name}."
                    else:
                        try:
                            result_content = json.dumps(result, default=str, indent=2)
                        except Exception:
                            result_content = str(result)
                except Exception as e:
                    result_content = f"Error in {tool_call['name']}: {e}"

            messages.append(
                ToolMessage(content=result_content, tool_call_id=tool_call["id"])
            )

    return Response(agent=current_agent, messages=messages[num_init_messages:])
