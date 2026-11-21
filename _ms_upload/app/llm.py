"""DeepSeek 客户端（OpenAI 兼容接口）。

契约见 docs/api.md §7：
    client = LLMClient(settings)
    client.available -> bool
    client.complete(messages) -> str        # 超时/401/断网抛 LLMUnavailable
    client.last_usage -> dict
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

from app.config import Settings, load_settings


class LLMUnavailable(RuntimeError):
    """模型不可用（无 key / 401 / 超时 / 断网），调用方负责降级。"""


class LLMClient:
    def __init__(self, settings: Settings | None = None, *, timeout: float | None = None):
        self.settings = settings or load_settings()
        self.timeout = float(timeout if timeout is not None else getattr(self.settings, "llm_timeout", 20.0))
        self.last_usage: Dict[str, Any] = {}
        self._lock = threading.Lock()
        self._client = None
        if self.settings.llm_configured:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(
                    api_key=self.settings.deepseek_api_key,
                    base_url=self.settings.deepseek_base_url,
                    timeout=self.timeout,
                    max_retries=0,
                )
            except Exception:  # pragma: no cover - SDK 缺失时安静降级
                self._client = None

    @property
    def model(self) -> str:
        return self.settings.deepseek_model

    @property
    def available(self) -> bool:
        return self._client is not None

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        timeout: float | None = None,
        retries: int = 2,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        if not self.available:
            raise LLMUnavailable("未配置 DEEPSEEK_API_KEY")

        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                with self._lock:
                    resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout or self.timeout,
                    )
                text = (resp.choices[0].message.content or "").strip()
                usage = getattr(resp, "usage", None)
                self.last_usage = {
                    "model": self.model,
                    "prompt_tokens": getattr(usage, "prompt_tokens", None),
                    "completion_tokens": getattr(usage, "completion_tokens", None),
                    "attempts": attempt + 1,
                }
                if not text:
                    raise LLMUnavailable("模型返回空文本")
                return text
            except Exception as exc:  # 401/超时/网络/空响应统一降级
                last_err = exc
                if attempt >= retries:
                    break
        raise LLMUnavailable(str(last_err))


class StubLLM:
    """测试用：固定返回或固定抛错。"""

    def __init__(self, text: str = "", *, raise_error: bool = False, usage: dict | None = None):
        self.text = text
        self.raise_error = raise_error
        self.last_usage = usage or {}
        self.calls = 0

    @property
    def available(self) -> bool:
        return not self.raise_error

    def complete(self, messages: List[Dict[str, str]], **_: Any) -> str:
        self.calls += 1
        if self.raise_error:
            raise LLMUnavailable("stub")
        return self.text
