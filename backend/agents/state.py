from typing import Optional
from langgraph.graph import MessagesState


class AgentState(MessagesState):
    """Shared state for the CogniCap agent graph.

    Extends MessagesState which provides:
        messages: Annotated[list[BaseMessage], add_messages]

    Additional fields carry routing decisions and user context.
    """
    next_agent: Optional[str]
    access_token: Optional[str]
    session_id: Optional[str]
