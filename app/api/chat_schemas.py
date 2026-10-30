from typing import Any

from pydantic import BaseModel, ConfigDict, Field

ConversationId = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$", description="An id returned by an earlier response")


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"message": "Переведите Алину из 3А в 3Б", "conversation_id": None}}
    )

    message: str = Field(min_length=1, max_length=2000, description="What the user typed")
    conversation_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description="Omit to start a new conversation; send the id from the previous response to continue it",
    )


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"conversation_id": "c_0123456789abcdef", "token": "…", "approve": True}}
    )

    conversation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    token: str = Field(max_length=64, description="The token on the confirmation card")
    approve: bool = Field(default=True, description="true = Confirm button, false = Cancel button")


class ChatMeta(BaseModel):
    request_type: str = Field(description="add, remove, transfer, show, search, missing_student, duplicate, off_topic, ...")
    outcome: str = Field(description="resolved, permission_denied, needs_clarification, out_of_scope or error")
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    duration_ms: int


class ChatResponse(BaseModel):
    conversation_id: str
    text: str = Field(description="The agent's answer, in the user's language")
    blocks: list[dict[str, Any]] = Field(
        description="Cards for the app to draw under the text. Each has a `type`; see the list in the "
        "description of POST /chat."
    )
    meta: ChatMeta


class HistoryMessage(BaseModel):
    role: str = Field(description="user or assistant")
    text: str
    blocks: list[dict[str, Any]]
    at: str | None


class HistoryResponse(BaseModel):
    conversation_id: str | None = Field(description="None when the user has no conversation yet")
    messages: list[HistoryMessage]
