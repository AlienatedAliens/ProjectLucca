"""
Tests for LLMClient concurrency and targeted abort state (F-BRAIN-006, Spec 10).
"""

import threading
import time
from unittest.mock import MagicMock, patch

from lucca.brain.llm_client import LLMClient
from lucca.core.schemas import Done, LLMEvent, TokenDelta


def test_abort_targets_only_matching_stream() -> None:
    """
    F-BRAIN-006: Targeted abort must abort ONLY the matching stream.
    Two scripted streams on one LLMClient with staggered starts.
    Abort trace A; assert B's generator continues to Done.
    """
    client = LLMClient(base_url="http://fake-llm:8080")

    stream_a_events: list[LLMEvent] = []
    stream_b_events: list[LLMEvent] = []
    stream_a_started = threading.Event()
    stream_b_started = threading.Event()

    def fake_stream_post(
        self, method: str, url: str, json: dict[str, object] | None = None, **kwargs: object
    ):  # type: ignore[no-untyped-def]
        payload = json or {}
        messages = payload.get("messages", [])
        content = ""
        if isinstance(messages, list):
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "user":
                    content = str(m.get("content", ""))

        is_a = "turn-A" in content

        class FakeResponse:
            status_code = 200

            def iter_lines(self):  # type: ignore[no-untyped-def]
                if is_a:
                    stream_a_started.set()
                    yield 'data: {"choices": [{"delta": {"content": "tokA1"}}]}'
                    time.sleep(0.05)
                    yield 'data: {"choices": [{"delta": {"content": "tokA2"}}]}'
                    time.sleep(0.5)  # Will be aborted here
                    yield 'data: {"choices": [{"delta": {"content": "tokA3"}}]}'
                    yield "data: [DONE]"
                else:
                    stream_b_started.set()
                    yield 'data: {"choices": [{"delta": {"content": "tokB1"}}]}'
                    time.sleep(0.05)
                    yield 'data: {"choices": [{"delta": {"content": "tokB2"}}]}'
                    yield "data: [DONE]"

            def __enter__(self):  # type: ignore[no-untyped-def]
                return self

            def __exit__(self, *args: object):  # type: ignore[no-untyped-def]
                pass

        return FakeResponse()

    with (
        patch("httpx.Client.stream", fake_stream_post),
        patch("httpx.Client.post", return_value=MagicMock(status_code=200)),
    ):

        def run_stream_a() -> None:
            for ev in client.stream_turn(current_text="turn-A", trace_id="trace-A"):
                stream_a_events.append(ev)

        def run_stream_b() -> None:
            for ev in client.stream_turn(current_text="turn-B", trace_id="trace-B"):
                stream_b_events.append(ev)

        t_a = threading.Thread(target=run_stream_a)
        t_b = threading.Thread(target=run_stream_b)

        t_a.start()
        assert stream_a_started.wait(timeout=2.0), "Stream A failed to start"

        # Stagger start stream B
        t_b.start()
        assert stream_b_started.wait(timeout=2.0), "Stream B failed to start"

        # Abort ONLY trace A
        client.abort(trace_id="trace-A")

        t_a.join(timeout=3.0)
        t_b.join(timeout=3.0)

        assert not t_a.is_alive(), "Stream A thread did not terminate"
        assert not t_b.is_alive(), "Stream B thread did not terminate"

        # Stream A was aborted: it must NOT have reached Done
        assert not any(isinstance(ev, Done) for ev in stream_a_events), (
            "Stream A unexpectedly reached Done"
        )

        # Stream B was NOT aborted: it MUST reach Done
        assert any(isinstance(ev, Done) for ev in stream_b_events), (
            "Stream B was erroneously aborted"
        )
        tokens_b = [ev.delta for ev in stream_b_events if isinstance(ev, TokenDelta)]
        assert "tokB1" in tokens_b
        assert "tokB2" in tokens_b


def test_persistent_connection_pool_reuses_client() -> None:
    """Verify that LLMClient retains its HTTP client pool across multiple turns."""
    client = LLMClient(base_url="http://fake-llm:8080")
    initial_http_client = client.http_client
    assert initial_http_client is not None
    assert not initial_http_client.is_closed

    class SimpleFakeResponse:
        status_code = 200

        def iter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
            yield "data: [DONE]"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    with (
        patch.object(initial_http_client, "stream", return_value=SimpleFakeResponse()),
        patch("httpx.Client.post", return_value=MagicMock(status_code=200)),
    ):
        events1 = list(client.stream_turn(current_text="turn 1"))
        assert any(isinstance(e, TokenDelta) and e.delta == "ok" for e in events1)
        # Client pool MUST remain open after turn 1
        assert not initial_http_client.is_closed
        assert client.http_client is initial_http_client

        events2 = list(client.stream_turn(current_text="turn 2"))
        assert any(isinstance(e, TokenDelta) and e.delta == "ok" for e in events2)
        # Client pool MUST remain open after turn 2
        assert not initial_http_client.is_closed
        assert client.http_client is initial_http_client

    client.close()
    assert initial_http_client.is_closed
    assert client._client is None
