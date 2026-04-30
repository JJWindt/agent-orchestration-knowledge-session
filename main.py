from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

from agent import Agent, run_full_turn

load_dotenv()


# ---------------------------------------------------------------------------
# Tools — add your own functions here
# ---------------------------------------------------------------------------

def get_weather(city: str) -> dict:
    """Return the current weather for a city."""
    # Replace this stub with a real API call if you like.
    return {"city": city, "temperature_c": 18, "condition": "partly cloudy"}

# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

agent = Agent(
    name="Assistant",
    instructions="You are a helpful assistant. Use your tools when relevant.",
    tools=[get_weather],
    llm=ChatOpenAI(model="gpt-5.2", temperature=0),
)


# ---------------------------------------------------------------------------
# Conversation loop
# ---------------------------------------------------------------------------

def main():
    messages = []
    current_agent = agent

    print(f"Chatting with {current_agent.name}. Type 'quit' to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in {"quit", "exit", "q"}:
            print("Goodbye!")
            break

        if not user_input:
            continue

        messages.append(HumanMessage(content=user_input))
        response = run_full_turn(current_agent, messages)

        current_agent = response.agent
        messages.extend(response.messages)
        print()


if __name__ == "__main__":
    main()
