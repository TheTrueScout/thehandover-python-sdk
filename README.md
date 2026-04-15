# The Handover — Python SDK

Human-in-the-loop approval SDK for AI agents. Stop agents from taking destructive actions without human sign-off.

## Install

```bash
pip install the-handover
```

With framework integrations:

```bash
pip install the-handover[langchain]
pip install the-handover[crewai]
pip install the-handover[openai]
pip install the-handover[all]
```

## Quick Start

```python
from the_handover import HandoverClient, DecisionDenied

client = HandoverClient(api_key="ho_live_...")

try:
    decision = client.approve(
        action="Delete 500 user records",
        approver="admin@company.com",
        urgency="critical",
    )
    print(f"Approved by {decision.resolved_by}")
    # Proceed with action...
except DecisionDenied as e:
    print(f"Denied: {e}")
    # Agent is STOPPED — cannot proceed
```

## Rich Responses

Ask for more than yes/no:

```python
from the_handover import HandoverClient, ChooseResponse

client = HandoverClient(api_key="ho_live_...")

decision = client.approve(
    action="Select deployment target",
    approver="ops@company.com",
    response_type=ChooseResponse(
        choices=["staging", "production", "canary"],
        label="Which environment?",
    ),
)
print(f"Deploying to: {decision.response_data['chosen']}")
```

## Enforcement with Decorators

```python
from the_handover import HandoverClient, require_approval

client = HandoverClient(api_key="ho_live_...")

@require_approval(client, approver="admin@company.com", urgency="critical")
def delete_all_users():
    db.execute("DELETE FROM users")

# This will NOT execute unless a human approves it.
# If denied, DecisionDenied is raised — the function never runs.
delete_all_users()
```

## LangChain

```python
from the_handover import HandoverClient
from the_handover.integrations.langchain import HandoverApprovalTool

client = HandoverClient(api_key="ho_live_...")
approval_tool = HandoverApprovalTool(client=client, approver="admin@company.com")

# Use in any LangChain agent
agent = create_react_agent(llm, [approval_tool, ...other_tools], prompt)
```

## CrewAI

```python
from the_handover import HandoverClient
from the_handover.integrations.crewai import HandoverApprovalTool

client = HandoverClient(api_key="ho_live_...")
tool = HandoverApprovalTool(client=client, approver="admin@company.com")

agent = Agent(role="Operations Manager", tools=[tool], ...)
```

## OpenAI

```python
from the_handover import HandoverClient
from the_handover.integrations.openai import handover_tool_definition, handle_handover_call

client = HandoverClient(api_key="ho_live_...")

# Add to your tools list
tools = [handover_tool_definition()]

# In your tool call handler
result = handle_handover_call(client, tool_call.function.arguments, approver="admin@company.com")
```

## Docs

Full documentation at [thehandover.xyz/docs](https://thehandover.xyz/docs)
