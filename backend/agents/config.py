"""Centralized LLM factory — two providers only.

    provider="openai"  → GPT-4o-mini  (orchestration, routing, lightweight tasks)
    provider="claude"  → claude-sonnet-4-6  (financial analysis, conviction, synthesis)

Per-user BYOK keys are checked first; platform env vars are the fallback.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    _env_path = Path(__file__).resolve().parents[2] / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        load_dotenv()
except ImportError:
    pass

from langchain_openai import ChatOpenAI
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.messages import AIMessage, HumanMessage


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
            result = [{"role": "user", "content": str(messages)}]
        return result

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from anthropic import Anthropic
        client = Anthropic(api_key=self.api_key)
        formatted = self._format_messages(messages)

        if self.extended_thinking:
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

        text = next((b.text for b in resp.content if b.type == "text"), "")
        usage = {}
        if hasattr(resp, "usage") and resp.usage is not None:
            usage = {
                "input_tokens": getattr(resp.usage, "input_tokens", 0),
                "output_tokens": getattr(resp.usage, "output_tokens", 0),
            }
        return ChatResult(generations=[ChatGeneration(
            message=AIMessage(content=text, additional_kwargs={"usage": usage})
        )])

    def invoke(self, input, config=None, **kwargs):
        msgs = [HumanMessage(content=input)] if isinstance(input, str) else input
        return self._generate(msgs).generations[0].message

    async def ainvoke(self, input, config=None, **kwargs):
        return self.invoke(input, config=config, **kwargs)


class TrackingChatModel:
    """Thin proxy around an LLM that records token usage after each call."""

    def __init__(self, inner: BaseChatModel, pipeline: str, user_id: int | None, provider: str, model: str):
        self._inner = inner
        self._pipeline = pipeline
        self._user_id = user_id
        self._provider = provider
        self._model = model

    def _record(self, response) -> None:
        try:
            usage = {}
            if hasattr(response, "additional_kwargs"):
                usage = response.additional_kwargs.get("usage", {})
            elif hasattr(response, "generations"):
                first = response.generations[0].message
                usage = first.additional_kwargs.get("usage", {})
            from services.llm_usage_service import record_usage
            record_usage(
                user_id=self._user_id,
                pipeline=self._pipeline,
                provider=self._provider,
                model=self._model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        except Exception:
            pass  # usage tracking must never break the pipeline

    def invoke(self, input, config=None, **kwargs):
        result = self._inner.invoke(input, config=config, **kwargs)
        self._record(result)
        return result

    async def ainvoke(self, input, config=None, **kwargs):
        result = await self._inner.ainvoke(input, config=config, **kwargs)
        self._record(result)
        return result

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _get_user_api_key(user_id: int, provider: str) -> str:
    """Retrieve a per-user API key. Returns empty string if not configured."""
    if user_id is None:
        return ""
    try:
        from services.llm_key_service import get_llm_key
        return get_llm_key(user_id, provider) or ""
    except Exception:
        return ""


def _is_rockstar_plan(user_id: int) -> bool:
    """Return True if the user has selected the Rockstar plan."""
    if user_id is None:
        return False
    try:
        from services.tier_service import get_user_plan
        return get_user_plan(user_id) == "rockstar"
    except Exception:
        return False


def get_llm(
    temperature: float = 0.1,
    provider: str = "openai",
    extended_thinking: bool = False,
    thinking_budget: int = 8000,
    user_id: int = None,
    pipeline: str = "unknown",
    # Legacy param ignored (was Gemini model name)
    model_name: str = None,
):
    """Create an LLM instance.

    Args:
        temperature:       Sampling temperature. Ignored for Claude+extended_thinking
                           (Anthropic forces temperature=1.0 in that mode).
        provider:          "claude" | "openai".
                           claude  → claude-sonnet-4-6 (financial analysis, conviction, synthesis)
                           openai  → gpt-4o-mini (orchestration, routing, lightweight tasks)
        extended_thinking: When True and provider="claude", activates Claude's extended
                           thinking mode for deeper multi-step reasoning.
        thinking_budget:   Token budget for the thinking phase (only used when
                           extended_thinking=True).
        user_id:           When provided, per-user BYOK keys are checked first before
                           falling back to the global environment variable.
    """
    from constants import LLM_PROVIDER_CLAUDE, LLM_PROVIDER_OPENAI, CLAUDE_MODEL_DEFAULT

    is_rockstar = _is_rockstar_plan(user_id)

    if provider == LLM_PROVIDER_CLAUDE:
        user_key = _get_user_api_key(user_id, "anthropic")
        if user_key:
            print(f"[LLM] Using Claude ({CLAUDE_MODEL_DEFAULT}, user key)")
            inner = ClaudeChatModel(
                model_name=CLAUDE_MODEL_DEFAULT,
                temperature=temperature,
                api_key=user_key,
                extended_thinking=extended_thinking,
                thinking_budget=thinking_budget,
            )
            return TrackingChatModel(inner, pipeline, user_id, "anthropic", CLAUDE_MODEL_DEFAULT)
        if is_rockstar:
            raise ValueError(
                "BYOK_REQUIRED:anthropic — Lone Wolf plan requires your own Anthropic API key. "
                "Configure it in Account › AI Models."
            )
        platform_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not platform_key:
            raise ValueError(
                "[LLM] ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file to use Claude."
            )
        print(f"[LLM] Using Claude ({CLAUDE_MODEL_DEFAULT}, platform key), extended_thinking={extended_thinking}")
        inner = ClaudeChatModel(
            model_name=CLAUDE_MODEL_DEFAULT,
            temperature=temperature,
            api_key=platform_key,
            extended_thinking=extended_thinking,
            thinking_budget=thinking_budget,
        )
        return TrackingChatModel(inner, pipeline, user_id, "anthropic", CLAUDE_MODEL_DEFAULT)

    # Default: OpenAI
    user_key = _get_user_api_key(user_id, "openai")
    if user_key:
        inner = ChatOpenAI(model="gpt-4o-mini", api_key=user_key, temperature=temperature)
        return TrackingChatModel(inner, pipeline, user_id, "openai", "gpt-4o-mini")
    if is_rockstar:
        raise ValueError(
            "BYOK_REQUIRED:openai — Lone Wolf plan requires your own OpenAI API key. "
            "Configure it in Account › AI Models."
        )
    platform_key = os.getenv("OPENAI_API_KEY", "")
    if not platform_key:
        raise ValueError(
            "[LLM] OPENAI_API_KEY is not set. "
            "Add it to your .env file to use OpenAI."
        )
    print(f"[LLM] Using OpenAI (gpt-4o-mini, platform key)")
    inner = ChatOpenAI(model="gpt-4o-mini", api_key=platform_key, temperature=temperature)
    return TrackingChatModel(inner, pipeline, user_id, "openai", "gpt-4o-mini")
