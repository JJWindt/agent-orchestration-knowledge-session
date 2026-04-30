# Agent Orchestration Boilerplate

A minimal starting point for building AI agents with tool use and agent transfers.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # then add your OPENAI_API_KEY
python main.py
```

## Structure

| File | Purpose |
|------|---------|
| `agent.py` | `Agent` dataclass and `run_full_turn()` loop |
| `main.py` | Example agent with one tool; start here |

## Core concepts

**Agent** — a name, a system prompt, a list of tools, and an LLM.

```python
agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    tools=[get_weather],
    llm=ChatOpenAI(model="gpt-5.2", temperature=0),
)
```

**Tool** — any Python function with a docstring. The docstring becomes the tool description the LLM sees.

```python
def get_weather(city: str) -> dict:
    """Return the current weather for a city."""
    return {"city": city, "temperature_c": 18, "condition": "partly cloudy"}
```

**run_full_turn** — sends messages to the LLM, executes tool calls, and loops until the LLM stops calling tools.

```python
response = run_full_turn(agent, messages)
```

## Agent transfers

To hand off to another agent, return an `Agent` instance from a tool. `run_full_turn` detects this and switches agents automatically.

```python
def transfer_to_specialist() -> Agent:
    """Transfer the conversation to the specialist agent."""
    return specialist_agent
```

## Agent as a tool

To use an agent as a tool — where a sub-agent does work and returns its output to the calling agent — wrap `run_full_turn` in a regular function. The calling agent sees the sub-agent's final response as a tool result and continues from there.

```python
def run_agent_as_tool(agent: Agent, user_message: str) -> str:
    """Run an agent and return its final response as a string."""
    messages = [{"role": "user", "content": user_message}]
    response = run_full_turn(agent, messages)
    return response.messages[-1]["content"]
```

Then expose it as a closure so the parent agent can call it:

```python
researcher = Agent(
    name="Researcher",
    instructions="You are a research assistant. Answer questions thoroughly.",
    tools=[search_web],
    llm=ChatOpenAI(model="gpt-5.2", temperature=0),
)

def ask_researcher(question: str) -> str:
    """Delegate a research question to the researcher agent and return its answer."""
    return run_agent_as_tool(researcher, question)

orchestrator = Agent(
    name="Orchestrator",
    instructions="You coordinate tasks. Use ask_researcher for any research needs.",
    tools=[ask_researcher],
    llm=ChatOpenAI(model="gpt-5.2", temperature=0),
)
```

The key difference from a transfer: the orchestrator **keeps control** and can act on the sub-agent's output, call other tools, or call the same sub-agent again.
