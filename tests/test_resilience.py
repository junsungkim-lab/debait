"""
Unit tests for _call_with_resilience (Feature #2: Orchestrator 복원력)
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.orchestrator.runner import _call_with_resilience, ExecutionConfig
from app.providers.base import LLMResult


def make_result(text="ok"):
    return LLMResult(text=text, provider="openai", model="m",
                     input_tokens=10, output_tokens=5, cost_usd=0.0)


def run(coro):
    return asyncio.run(coro)


class TestCallWithResilience:
    def _cfg(self, retries=0, timeout=5):
        return ExecutionConfig(retries_per_stage=retries, stage_timeout_sec=timeout,
                               enable_quality_matrix=False)

    # ── 성공 케이스 ─────────────────────────────────────────────
    def test_success_returns_result(self):
        prov = MagicMock()
        prov.generate = AsyncMock(return_value=make_result("hello"))
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=0),
        ))
        assert result is not None
        assert result.text == "hello"
        assert rt["status"] == "ok"
        assert rt["retries"] == 0

    def test_success_first_attempt_no_retry(self):
        prov = MagicMock()
        prov.generate = AsyncMock(return_value=make_result())
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=2),
        ))
        assert prov.generate.call_count == 1
        assert rt["retries"] == 0

    # ── 재시도 케이스 ───────────────────────────────────────────
    def test_retry_on_failure_then_success(self):
        prov = MagicMock()
        prov.generate = AsyncMock(side_effect=[
            RuntimeError("first fail"),
            make_result("recovered"),
        ])
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=1),
        ))
        assert result is not None
        assert result.text == "recovered"
        assert rt["retries"] == 1
        assert rt["status"] == "ok"
        assert prov.generate.call_count == 2

    def test_all_retries_exhausted_returns_none(self):
        prov = MagicMock()
        prov.generate = AsyncMock(side_effect=RuntimeError("always fail"))
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=2),
        ))
        assert result is None
        assert rt["status"] == "failed"
        assert "error" in rt
        assert "always fail" in rt["error"]
        assert prov.generate.call_count == 3  # 1 + 2 retries

    def test_zero_retries_fails_immediately(self):
        prov = MagicMock()
        prov.generate = AsyncMock(side_effect=RuntimeError("fail"))
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=0),
        ))
        assert result is None
        assert prov.generate.call_count == 1

    # ── 타임아웃 케이스 ─────────────────────────────────────────
    def test_timeout_returns_none(self):
        import asyncio as aio

        async def slow(**kwargs):
            await aio.sleep(10)
            return make_result()

        prov = MagicMock()
        prov.generate = slow
        result, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(retries=0, timeout=1),
        ))
        assert result is None
        assert rt["status"] == "failed"

    # ── 런타임 딕셔너리 검증 ────────────────────────────────────
    def test_runtime_latency_measured(self):
        prov = MagicMock()
        prov.generate = AsyncMock(return_value=make_result())
        _, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(),
        ))
        assert rt["latency_ms"] >= 0

    def test_runtime_has_required_keys(self):
        prov = MagicMock()
        prov.generate = AsyncMock(return_value=make_result())
        _, rt = run(_call_with_resilience(
            provider=prov, api_key="key", model="m",
            system="s", user="u", max_tokens=100,
            cfg=self._cfg(),
        ))
        for key in ("latency_ms", "retries", "status"):
            assert key in rt
