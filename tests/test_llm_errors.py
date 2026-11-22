"""LLM 异常分类 / 重试退避 / 用量记录回归（task-5，完全离线）。

约束：
- 绝不触网：``LLMClient`` 构造后立刻用假对象替换 ``client._client``；
- 不真实等待：monkeypatch ``app.llm.time.sleep`` 记录退避时长；
- 绝不泄露 key：断言异常文本与 ``last_usage`` 中不含 ``sk-test`` / Authorization。
"""
from __future__ import annotations

from typing import Any

import pytest

import app.llm as llm
from app.config import Settings
from app.llm import LLMClient, LLMUnavailable, StubLLM

API_KEY = "sk-test"


# ---------------------------------------------------------------- 假响应
class _FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeMessage(content)


class _FakeUsage:
    prompt_tokens = 11
    completion_tokens = 7


class _FakeResponse:
    def __init__(self, content: str = "结论 [E1]") -> None:
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


# ---------------------------------------------------------------- 假异常（openai 风格）
class _ApiError(Exception):
    """模拟 openai.APIStatusError：带 status_code。"""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeAPITimeoutError(Exception):
    """类名含 Timeout（openai.APITimeoutError 风格，无 status_code）。"""


class _FakeAPIConnectionError(Exception):
    """类名含 Connection（openai.APIConnectionError 风格，无 status_code）。"""


class _AuthenticationError(Exception):
    """类名含 Authentication（部分 SDK 版本无 status_code 时兜底）。"""


class _RateLimitError(Exception):
    """类名含 RateLimit。"""


class _InternalServerError(Exception):
    """类名含 InternalServer。"""


class _BadRequestError(Exception):
    """类名含 BadRequest。"""


# ---------------------------------------------------------------- 假 client
class _FakeCompletions:
    def __init__(self, outcomes: list[Any]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def create(self, **kwargs: Any) -> Any:
        self.calls += 1
        if not self.outcomes:
            raise AssertionError(f"create 调用次数超出预期（第 {self.calls} 次），可能重试逻辑有误")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeChat:
    def __init__(self, completions: _FakeCompletions) -> None:
        self.completions = completions


class _FakeClient:
    def __init__(self, outcomes: list[Any]) -> None:
        self.completions = _FakeCompletions(outcomes)
        self.chat = _FakeChat(self.completions)


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    outcomes: list[Any],
) -> tuple[LLMClient, _FakeClient, list[float]]:
    client = LLMClient(settings=Settings(deepseek_api_key=API_KEY))
    fake = _FakeClient(outcomes)
    client._client = fake
    sleeps: list[float] = []
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: sleeps.append(float(seconds)))
    return client, fake, sleeps


def _complete(client: LLMClient, *, retries: int = 2) -> str:
    return client.complete([{"role": "user", "content": "阳光玫瑰怎么存？"}], retries=retries)


def _assert_usage(client: LLMClient, *, attempts: int, error: str | None) -> dict[str, Any]:
    usage = client.last_usage
    for key in ("model", "attempts", "latency_ms", "error", "prompt_tokens", "completion_tokens"):
        assert key in usage, f"last_usage 缺少 {key}：{usage}"
    assert usage["attempts"] == attempts
    assert usage["error"] == error
    assert usage["model"] == "deepseek-chat"
    assert isinstance(usage["latency_ms"], int) and usage["latency_ms"] >= 0
    assert API_KEY not in repr(usage), f"last_usage 不得记录 API key：{usage}"
    assert "Authorization" not in repr(usage)
    return usage


# ---------------------------------------------------------------- 分类单测
@pytest.mark.parametrize(
    "error, kind",
    [
        (_ApiError("Unauthorized", 401), "auth"),
        (_ApiError("Forbidden", 403), "auth"),
        (_ApiError("Too Many Requests", 429), "rate_limit"),
        (_ApiError("Internal Server Error", 500), "server"),
        (_ApiError("Bad Gateway", 502), "server"),
        (_ApiError("Request Timeout", 408), "timeout"),
        (_ApiError("Bad Request", 400), "bad_request"),
        (TimeoutError("timed out"), "timeout"),
        (_FakeAPITimeoutError("request timed out"), "timeout"),
        (RuntimeError("upstream read timeout"), "timeout"),
        (ConnectionError("connection reset"), "network"),
        (_FakeAPIConnectionError("connection error"), "network"),
        (_AuthenticationError("invalid api key"), "auth"),
        (_RateLimitError("slow down"), "rate_limit"),
        (_InternalServerError("upstream failed"), "server"),
        (_BadRequestError("invalid model"), "bad_request"),
        (RuntimeError("weird failure"), "unknown"),
    ],
)
def test_classify_error(error: BaseException, kind: str) -> None:
    assert llm.classify_error(error)[0] == kind


def test_backoff_is_exponential_and_capped() -> None:
    assert 0.5 <= llm.backoff_seconds(0) <= 0.61
    assert 1.0 <= llm.backoff_seconds(1) <= 1.11
    assert 2.0 <= llm.backoff_seconds(2) <= 2.11
    assert 4.0 <= llm.backoff_seconds(10) <= 4.11, "退避必须封顶 4s（+jitter）"


# ---------------------------------------------------------------- 不可重试：401/403
@pytest.mark.parametrize("status", [401, 403])
def test_auth_error_not_retried(monkeypatch: pytest.MonkeyPatch, status: int) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [_ApiError("Unauthorized", status)])

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    exc = caught.value
    assert fake.completions.calls == 1, "401/403 认证错误不允许重试"
    assert sleeps == [], "认证错误不应退避等待"
    assert exc.kind == "auth"
    assert exc.status_code == status
    assert f"auth: {status}" in str(exc), f"认证错误消息应形如 auth: {status} ...：{exc}"
    _assert_usage(client, attempts=1, error="auth")


def test_auth_error_redacts_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _fake, _sleeps = _make_client(
        monkeypatch, [_ApiError(f"invalid api key {API_KEY} leaked", 401)]
    )

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    exc = caught.value
    assert API_KEY not in str(exc), f"异常消息不得包含 API key：{exc}"
    assert API_KEY not in repr(exc), f"异常 repr 不得包含 API key：{exc!r}"
    assert "***" in str(exc), f"API key 应被脱敏为 ***：{exc}"


# ---------------------------------------------------------------- 可重试：429
def test_rate_limit_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [_ApiError("Too Many Requests", 429) for _ in range(3)]
    client, fake, sleeps = _make_client(monkeypatch, outcomes)

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client, retries=2)

    exc = caught.value
    assert fake.completions.calls == 3, "retries=2 → 429 应共尝试 3 次"
    assert len(sleeps) == 2, f"3 次尝试之间应退避 2 次：{sleeps}"
    assert sleeps[1] > sleeps[0] > 0, f"退避应递增：{sleeps}"
    assert all(delay <= llm.MAX_BACKOFF_SECONDS + llm.BACKOFF_JITTER_SECONDS for delay in sleeps)
    assert exc.kind == "rate_limit"
    assert exc.status_code == 429
    assert "rate_limit" in str(exc)
    _assert_usage(client, attempts=3, error="rate_limit")


def test_retries_zero_means_single_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [_ApiError("Too Many Requests", 429)])

    with pytest.raises(LLMUnavailable):
        _complete(client, retries=0)

    assert fake.completions.calls == 1, "retries=0 时只允许 1 次请求"
    assert sleeps == []


# ---------------------------------------------------------------- 可重试：超时
@pytest.mark.parametrize(
    "error_factory",
    [
        lambda: TimeoutError("timed out"),
        lambda: _FakeAPITimeoutError("request timed out"),
    ],
    ids=["builtin-timeout", "api-timeout-class"],
)
def test_timeout_retried_and_message_keeps_timeout_keyword(
    monkeypatch: pytest.MonkeyPatch, error_factory: Any
) -> None:
    outcomes = [error_factory() for _ in range(3)]
    client, fake, sleeps = _make_client(monkeypatch, outcomes)

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    exc = caught.value
    assert fake.completions.calls == 3, "超时属于可重试错误"
    assert len(sleeps) == 2
    assert exc.kind == "timeout"
    assert "timeout" in str(exc).lower(), f"qa 依赖消息中的 timeout 关键字降级为 llm_timeout：{exc}"
    _assert_usage(client, attempts=3, error="timeout")


# ---------------------------------------------------------------- 可重试：5xx（第 2 次成功）
def test_server_5xx_retried_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(
        monkeypatch,
        [_ApiError("Internal Server Error", 500), _FakeResponse("结论：0±0.5℃ [E1]")],
    )

    text = _complete(client)

    assert text == "结论：0±0.5℃ [E1]"
    assert fake.completions.calls == 2
    assert len(sleeps) == 1
    usage = _assert_usage(client, attempts=2, error=None)
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 7


# ---------------------------------------------------------------- 可重试：网络
def test_network_error_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes = [_FakeAPIConnectionError("connection reset") for _ in range(3)]
    client, fake, sleeps = _make_client(monkeypatch, outcomes)

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    exc = caught.value
    assert fake.completions.calls == 3
    assert len(sleeps) == 2
    assert exc.kind == "network"
    assert "network" in str(exc)
    _assert_usage(client, attempts=3, error="network")


# ---------------------------------------------------------------- 不可重试：其它 4xx / 未知
def test_bad_request_4xx_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [_ApiError("model not found", 404)])

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    assert fake.completions.calls == 1
    assert sleeps == []
    assert caught.value.kind == "bad_request"
    assert "bad_request" in str(caught.value)
    _assert_usage(client, attempts=1, error="bad_request")


def test_unknown_error_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [RuntimeError("boom")])

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client)

    assert fake.completions.calls == 1, "无法识别的错误不得重复请求"
    assert sleeps == []
    assert caught.value.kind == "unknown"
    assert "unknown" in str(caught.value)
    _assert_usage(client, attempts=1, error="unknown")


# ---------------------------------------------------------------- 成功路径 / 降级语义
def test_success_first_attempt_records_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [_FakeResponse("答案 [E1]")])

    assert _complete(client) == "答案 [E1]"
    assert fake.completions.calls == 1
    assert sleeps == []
    usage = _assert_usage(client, attempts=1, error=None)
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 7


def test_empty_text_falls_back_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    client, fake, sleeps = _make_client(monkeypatch, [_FakeResponse(""), _FakeResponse("  ")])

    with pytest.raises(LLMUnavailable) as caught:
        _complete(client, retries=1)

    assert fake.completions.calls == 2
    assert len(sleeps) == 1
    assert "空文本" in str(caught.value)
    assert caught.value.kind == "unknown"


def test_unavailable_without_key_degrades() -> None:
    client = LLMClient(settings=Settings(deepseek_api_key=""))
    assert client.available is False
    with pytest.raises(LLMUnavailable):
        client.complete([{"role": "user", "content": "hi"}])
    assert client.last_usage == {}


def test_llm_unavailable_attributes_default() -> None:
    exc = LLMUnavailable("x")
    assert isinstance(exc, RuntimeError)
    assert exc.kind == "unknown"
    assert exc.status_code is None


def test_stub_llm_unchanged() -> None:
    stub = StubLLM("固定文本")
    assert stub.available is True
    assert stub.complete([]) == "固定文本"
    assert stub.calls == 1
    assert stub.last_usage == {}

    broken = StubLLM("", raise_error=True)
    assert broken.available is False
    with pytest.raises(LLMUnavailable):
        broken.complete([])
    assert broken.calls == 1
