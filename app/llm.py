"""DeepSeek 客户端（OpenAI 兼容接口）。

契约见 docs/api.md §7：
    client = LLMClient(settings)
    client.available -> bool
    client.complete(messages) -> str        # 超时/401/断网抛 LLMUnavailable
    client.last_usage -> dict

错误分类（不依赖 openai 包，按 status_code / 异常类名 / 消息识别）：
    auth(401/403) / rate_limit(429) / server(5xx) / timeout / network / bad_request(其它 4xx) / unknown
其中 rate_limit、server、timeout、network 可重试（指数退避）；其余（含无法识别）只请求一次。
异常对象附加 ``kind`` / ``status_code`` 属性，消息与 ``last_usage`` 均不含 API key。
"""
from __future__ import annotations

import random
import re
import threading
import time
from typing import Any

from app.config import Settings, load_settings

KIND_AUTH = "auth"
KIND_RATE_LIMIT = "rate_limit"
KIND_SERVER = "server"
KIND_TIMEOUT = "timeout"
KIND_NETWORK = "network"
KIND_BAD_REQUEST = "bad_request"
KIND_UNKNOWN = "unknown"

#: 可重试的错误类别（指数退避后最多按 retries 参数重试）
RETRYABLE_KINDS = frozenset({KIND_RATE_LIMIT, KIND_SERVER, KIND_TIMEOUT, KIND_NETWORK})
#: 认证类状态码（不可重试）
AUTH_STATUS_CODES = frozenset({401, 403})

BASE_BACKOFF_SECONDS = 0.5
MAX_BACKOFF_SECONDS = 4.0
BACKOFF_JITTER_SECONDS = 0.1
ERROR_DETAIL_LIMIT = 200

# 异常文本里可能出现的 API key 形态（精确 key 之外再兜底脱敏）
_REDACT_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]+")

_KIND_REASONS = {
    KIND_AUTH: "DeepSeek 认证失败（API key 无效或无权限）",
    KIND_RATE_LIMIT: "请求被限流（429，稍后重试）",
    KIND_SERVER: "DeepSeek 服务端异常（5xx）",
    KIND_TIMEOUT: "请求超时未返回",
    KIND_NETWORK: "网络连接失败（断网或无法连接 DeepSeek）",
    KIND_BAD_REQUEST: "请求被拒绝（4xx，参数或模型名非法）",
    KIND_UNKNOWN: "未识别的模型错误",
}


class LLMUnavailable(RuntimeError):
    """模型不可用（无 key / 401 / 超时 / 断网），调用方负责降级。

    附加属性（供上层日志/指标使用）：
        kind: auth / rate_limit / server / timeout / network / bad_request / unknown
        status_code: HTTP 状态码；异常里拿不到时为 None
    """

    def __init__(self, message: str = "", *, kind: str = KIND_UNKNOWN, status_code: int | None = None) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code


def _status_code_of(exc: BaseException) -> int | None:
    """尽量从异常本身或 ``exc.response`` 取 HTTP 状态码，取不到返回 None。"""
    code = getattr(exc, "status_code", None)
    if code is None:
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None) if response is not None else None
    if code is None:
        return None
    try:
        return int(code)
    except (TypeError, ValueError):
        return None


def classify_error(exc: BaseException) -> tuple[str, int | None]:
    """把 openai 风格异常归类为 ``(kind, status_code)``；纯标准库实现，便于离线测试。"""
    status = _status_code_of(exc)
    if status in AUTH_STATUS_CODES:
        return KIND_AUTH, status
    if status == 429:
        return KIND_RATE_LIMIT, status
    if status is not None and 500 <= status <= 599:
        return KIND_SERVER, status
    if status == 408:  # Request Timeout 也按超时处理
        return KIND_TIMEOUT, status
    if status is not None and 400 <= status <= 499:
        return KIND_BAD_REQUEST, status
    # 无状态码：按异常类名 / 消息识别超时、网络与 openai 风格异常
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in name or "timeout" in message:
        return KIND_TIMEOUT, status
    if "authentication" in name or "permissiondenied" in name or "unauthorized" in name:
        return KIND_AUTH, status
    if "ratelimit" in name or "rate_limit" in name:
        return KIND_RATE_LIMIT, status
    if "internalserver" in name or "serviceunavailable" in name:
        return KIND_SERVER, status
    if "badrequest" in name or "notfound" in name or "unprocessable" in name:
        return KIND_BAD_REQUEST, status
    if (
        isinstance(exc, ConnectionError)
        or "connection" in name
        or "connection" in message
        or "network" in name
        or "network" in message
    ):
        return KIND_NETWORK, status
    return KIND_UNKNOWN, status


def is_retryable(kind: str) -> bool:
    return kind in RETRYABLE_KINDS


def backoff_seconds(attempt: int) -> float:
    """第 ``attempt`` 次（0 起）失败后的等待秒数：min(4, 0.5 * 2**attempt) + 小幅 jitter。"""
    base = min(MAX_BACKOFF_SECONDS, BASE_BACKOFF_SECONDS * (2 ** max(0, attempt)))
    return base + random.uniform(0.0, BACKOFF_JITTER_SECONDS)


def _redact(text: str, api_key: str = "") -> str:
    """去掉异常文本里的 API key（精确值 + sk- 形态）并压成单行短摘要。"""
    if not text:
        return ""
    if api_key:
        text = text.replace(api_key, "***")
    text = _REDACT_PATTERN.sub("sk-***", text)
    return " ".join(text.split())[:ERROR_DETAIL_LIMIT]


class LLMClient:
    def __init__(self, settings: Settings | None = None, *, timeout: float | None = None):
        self.settings = settings or load_settings()
        self.timeout = float(timeout if timeout is not None else getattr(self.settings, "llm_timeout", 20.0))
        self.last_usage: dict[str, Any] = {}
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

    def _record_usage(
        self,
        *,
        attempts: int,
        latency_ms: int,
        error: str | None,
        usage: Any = None,
    ) -> None:
        """记录本次调用元信息；绝不写入 api_key / Authorization。"""
        self.last_usage = {
            "model": self.model,
            "attempts": attempts,
            "latency_ms": latency_ms,
            "error": error,
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage is not None else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage is not None else None,
        }

    def _unavailable(self, kind: str, status: int | None, attempts: int, exc: BaseException) -> LLMUnavailable:
        api_key = str(getattr(self.settings, "deepseek_api_key", "") or "")
        reason = _KIND_REASONS.get(kind, "模型调用失败")
        head = f"{kind}: {status}" if status is not None else kind
        retry_note = f"（已尝试 {attempts} 次）" if attempts > 1 else "（未重试）"
        detail = _redact(str(exc), api_key)
        tail = f"：{type(exc).__name__}" + (f": {detail}" if detail else "")
        return LLMUnavailable(f"{head} {reason}{retry_note}{tail}", kind=kind, status_code=status)

    def _sleep_before_retry(self, attempt: int) -> None:
        # 模块级 time.sleep：测试里可 monkeypatch app.llm.time.sleep 避免真实等待
        time.sleep(backoff_seconds(attempt))

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        timeout: float | None = None,
        retries: int = 2,
        temperature: float = 0.2,
        max_tokens: int = 600,
    ) -> str:
        if not self.available:
            raise LLMUnavailable("未配置 DEEPSEEK_API_KEY")

        try:
            total_attempts = max(0, int(retries)) + 1
        except (TypeError, ValueError):
            total_attempts = 3

        started = time.perf_counter()
        for attempt in range(total_attempts):
            attempts = attempt + 1
            try:
                with self._lock:
                    resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout or self.timeout,
                    )
            except Exception as exc:  # 统一分类后决定重试或降级
                kind, status = classify_error(exc)
                if is_retryable(kind) and attempt < total_attempts - 1:
                    self._sleep_before_retry(attempt)
                    continue
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._record_usage(attempts=attempts, latency_ms=latency_ms, error=kind)
                raise self._unavailable(kind, status, attempts, exc) from None

            text = (resp.choices[0].message.content or "").strip()
            usage = getattr(resp, "usage", None)
            if not text:
                # 空文本按旧行为重试（可能是瞬时抖动），耗尽后按未知错误降级
                if attempt < total_attempts - 1:
                    self._sleep_before_retry(attempt)
                    continue
                latency_ms = int((time.perf_counter() - started) * 1000)
                self._record_usage(attempts=attempts, latency_ms=latency_ms, error=KIND_UNKNOWN)
                raise LLMUnavailable("模型返回空文本", kind=KIND_UNKNOWN) from None

            latency_ms = int((time.perf_counter() - started) * 1000)
            self._record_usage(attempts=attempts, latency_ms=latency_ms, error=None, usage=usage)
            return text

        # 理论上不可达（循环内要么 return 要么 raise），保留兜底
        latency_ms = int((time.perf_counter() - started) * 1000)
        self._record_usage(attempts=max(1, total_attempts), latency_ms=latency_ms, error=KIND_UNKNOWN)
        raise LLMUnavailable("模型调用失败", kind=KIND_UNKNOWN)


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

    def complete(self, messages: list[dict[str, str]], **_: Any) -> str:
        self.calls += 1
        if self.raise_error:
            raise LLMUnavailable("stub")
        return self.text
