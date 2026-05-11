"""
Tenant-aware agent state.

Inspired by langgraph-sales-agent's SalesAgentState: messages stay generic,
while runtime context such as tenant/channel/user is injected through graph
input/config instead of being hardcoded into prompts.
"""

from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class KobiAgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    tenant_id: int
    channel: str
    channel_user_id: str
