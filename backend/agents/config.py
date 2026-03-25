"""Centralized LLM factory with automatic Gemini → OpenAI fallback.

When Gemini hits rate limits (429 / RESOURCE_EXHAUSTED / quota errors),
calls are automatically retried using ChatGPT as a fallback.
Implements manual fallback wrapper because LangChain's with_fallbacks()
has compatibility issues with Python 3.14 / Pydantic V1.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    # Ensure .env is loaded (may live one level above backend/)
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        load_dotenv()  # fallback: search from cwd upward
except ImportError:
    # dotenv already loaded by app.py before agents are imported
    pass

from typing import Any as TypingAny

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage, HumanMessage

# Map Gemini model names to comparable OpenAI models
_FALLBACK_MODEL_MAP = {
    "gemini-2.5-flash": "gpt-4o-mini",
    "gemini-2.0-flash": "gpt-4o-mini",
    "gemini-1.5-pro": "gpt-4o",
}


class FallbackChatModel(BaseChatModel):
    """Chat model that tries primary, falls back to secondary on any error.

    Uses ``Any`` for inner models so it can also wrap ``RunnableBinding``
    objects returned by ``bind_tools()``.
    """

    primary: TypingAny = None
    fallback: TypingAny = None
    primary_name: str = "primary"
    fallback_name: str = "fallback"

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "fallback-chat-model"

    # -- low-level path (called by BaseChatModel.generate) ----------------
    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        try:
            if hasattr(self.primary, "_generate"):
                return self.primary._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            # RunnableBinding (from bind_tools) — use invoke
            result = self.primary.invoke(messages)
            return ChatResult(generations=[ChatGeneration(message=result)])
        except Exception as e:
            print(f"[LLM] {self.primary_name} _generate failed: {str(e)[:120]}")
            print(f"[LLM] Falling back to {self.fallback_name}...")
            if hasattr(self.fallback, "_generate"):
                return self.fallback._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
            result = self.fallback.invoke(messages)
            return ChatResult(generations=[ChatGeneration(message=result)])

    # -- high-level path (used by LangGraph / create_react_agent) ---------
    def invoke(self, input, config=None, **kwargs):
        try:
            return self.primary.invoke(input, config=config, **kwargs)
        except Exception as e:
            print(f"[LLM] {self.primary_name} invoke failed: {str(e)[:120]}")
            print(f"[LLM] Falling back to {self.fallback_name}...")
            return self.fallback.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        try:
            return await self.primary.ainvoke(input, config=config, **kwargs)
        except Exception as e:
            print(f"[LLM] {self.primary_name} ainvoke failed: {str(e)[:120]}")
            print(f"[LLM] Falling back to {self.fallback_name}...")
            return await self.fallback.ainvoke(input, config=config, **kwargs)

    # -- tool binding (for create_react_agent) ----------------------------
    def bind_tools(self, tools, **kwargs):
        bound_primary = self.primary.bind_tools(tools, **kwargs)
        bound_fallback = self.fallback.bind_tools(tools, **kwargs)
        return FallbackChatModel(
            primary=bound_primary,
            fallback=bound_fallback,
            primary_name=self.primary_name,
            fallback_name=self.fallback_name,
        )


class ClaudeChatModel(BaseChatModel):
    """Anthropic Claude wrapper with optional extended thinking support.

    Uses the direct ``anthropic`` SDK rather than ``langchain-anthropic`` because
    extended thinking requires the ``thinking`` parameter which the LangChain
    wrapper does not yet expose cleanly.

    NOTE: When ``extended_thinking=True``, Anthropic's API requires
    ``temperature=1.0`` regardless of the value passed to ``get_llm()``.
    """

    model_name: str = "claude-sonnet-4-6"
    temperature: float = 0.1
    api_key: str = ""
    extended_thinking: bool = False
    thinking_budget: int = 8000

    class Config:
        arbitrary_types_allowed = True

    @property
    def _llm_type(self) -> str:
        return "claude-chat-model"

    def _format_messages(self, messages) -> list[dict]:
        """Convert LangChain messages to Anthropic API format."""
        result = []
        for m in messages:
            cls = m.__class__.__name__
            if cls == "SystemMessage":
                continue  # Anthropic system messages handled separately; skip here
            role = "assistant" if cls == "AIMessage" else "user"
            content = m.content if hasattr(m, "content") else str(m)
            result.append({"role": role, "content": content})
        if not result:
            # Fallback: treat entire input as a user message
            result = [{"role": "user", "content": str(messages)}]
        return result

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        formatted = self._format_messages(messages)

        if self.extended_thinking:
            # Extended thinking requires temperature=1.0 (Anthropic requirement)
            resp = client.messages.create(
                model=self.model_name,
                max_tokens=16000,
                thinking={"type": "enabled", "budget_tokens": self.thinking_budget},
                messages=formatted,
                temperature=1.0,
            )
        else:
            resp = client.messages.create(
                model=self.model_name,
                max_tokens=4096,
                messages=formatted,
                temperature=self.temperature,
            )

        # Extract text content only (skip thinking blocks)
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    def invoke(self, input, config=None, **kwargs):
        msgs = [HumanMessage(content=input)] if isinstance(input, str) else input
        return self._generate(msgs).generations[0].message

    async def ainvoke(self, input, config=None, **kwargs):
        # Sync fallback — sufficient for current usage patterns
        return self.invoke(input, config=config, **kwargs)


def get_llm(
    model_name: str = "gemini-2.5-flash",
    temperature: float = 0.1,
    provider: str = None,
    extended_thinking: bool = False,
    thinking_budget: int = 8000,
):
    """Create an LLM instance.

    Args:
        model_name:        Gemini model name (used only when provider is None/"gemini").
        temperature:       Sampling temperature. Ignored for Claude+extended_thinking
                           (Anthropic forces temperature=1.0 in that mode).
        provider:          "gemini" | "claude" | "openai" | None.
                           None / "gemini" → existing Gemini+OpenAI fallback (unchanged).
        extended_thinking: When True and provider="claude", activates Claude's extended
                           thinking mode for deeper multi-step reasoning.
        thinking_budget:   Token budget for the thinking phase (only used when
                           extended_thinking=True).
    """
    from constants import LLM_PROVIDER_CLAUDE, LLM_PROVIDER_OPENAI, CLAUDE_MODEL_DEFAULT

    if provider == LLM_PROVIDER_CLAUDE:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not anthropic_key:
            print("[LLM] WARNING: ANTHROPIC_API_KEY not set — falling back to Gemini")
        else:
            print(
                f"[LLM] Using Claude ({CLAUDE_MODEL_DEFAULT}), "
                f"extended_thinking={extended_thinking}, budget={thinking_budget}"
            )
            return ClaudeChatModel(
                model_name=CLAUDE_MODEL_DEFAULT,
                temperature=temperature,
                api_key=anthropic_key,
                extended_thinking=extended_thinking,
                thinking_budget=thinking_budget,
            )

    if provider == LLM_PROVIDER_OPENAI:
        openai_key = os.getenv("OPENAI_API_KEY", "")
        if not openai_key:
            print("[LLM] WARNING: OPENAI_API_KEY not set — falling back to Gemini")
        else:
            return ChatOpenAI(model="gpt-4o-mini", api_key=openai_key, temperature=temperature)

    # Default path: Gemini with automatic OpenAI fallback (original behaviour)
    gemini_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    primary = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=gemini_key,
        temperature=temperature,
    )

    if not openai_key:
        print("[LLM] WARNING: OPENAI_API_KEY not found — no fallback available")
        return primary

    fallback_model = _FALLBACK_MODEL_MAP.get(model_name, "gpt-4o-mini")
    fallback = ChatOpenAI(
        model=fallback_model,
        api_key=openai_key,
        temperature=temperature,
    )

    print(f"[LLM] Configured {model_name} with fallback to {fallback_model}")
    return FallbackChatModel(
        primary=primary,
        fallback=fallback,
        primary_name=model_name,
        fallback_name=fallback_model,
    )
