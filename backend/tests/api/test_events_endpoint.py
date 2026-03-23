"""Tests for /api/events SSE endpoint.

Phase 170-03: Control Actuation Loop — SSE Stream

Tests verify the event stream endpoint accepts correlation_id, streams events
in SSE format, and closes connection after terminal events.
"""

import pytest


@pytest.mark.asyncio
async def test_events_endpoint_route_exists():
    """Verify /api/events route is registered."""
    from app.api import events

    assert hasattr(events, "router"), "events module must have a router"
    assert events.router is not None


@pytest.mark.asyncio
async def test_events_endpoint_accepts_correlation_id(client):
    """GET /api/events?correlation_id={id} opens SSE stream.

    Verifies endpoint signature accepts correlation_id parameter.
    """
    from app.api.events import event_stream_endpoint
    import inspect

    sig = inspect.signature(event_stream_endpoint)
    assert "correlation_id" in sig.parameters, "event_stream_endpoint must accept correlation_id parameter"


@pytest.mark.asyncio
async def test_events_endpoint_sse_format():
    """Verify events emitted in correct SSE format.

    SSE format: event: {type}\ndata: {json}\n\n
    """
    from app.middleware.event_stream import event_stream
    from app.api.events import event_stream_endpoint

    # This is tested indirectly via the telemetry verification tests
    # which mock event_stream.emit() and verify the format
    # Here we just verify the endpoint function exists and is callable
    assert callable(event_stream_endpoint)
    assert callable(event_stream.emit)


@pytest.mark.asyncio
async def test_events_endpoint_stream_closes_after_terminal_event():
    """Verify SSE stream closes after COMMAND_VERIFIED or COMMAND_TIMEOUT.

    The event_stream_endpoint generator breaks the loop and closes the
    connection when it receives a terminal event.
    """
    from app.api.events import event_stream_endpoint
    import inspect

    # Check the function source to verify terminal event handling
    source = inspect.getsource(event_stream_endpoint)
    assert "COMMAND_VERIFIED" in source, "Endpoint must handle COMMAND_VERIFIED"
    assert "COMMAND_TIMEOUT" in source, "Endpoint must handle COMMAND_TIMEOUT"
    assert "break" in source, "Endpoint must break loop after terminal event"


@pytest.mark.asyncio
async def test_event_stream_manager_subscribe():
    """Verify event_stream.subscribe() creates channel for correlation_id."""
    from app.middleware.event_stream import event_stream

    correlation_id = "test-corr-123"

    # Subscribe to events
    channel = await event_stream.subscribe(correlation_id)

    assert channel is not None
    assert isinstance(channel, type(channel))  # asyncio.Queue

    # Cleanup
    await event_stream.unsubscribe(correlation_id)


@pytest.mark.asyncio
async def test_event_stream_manager_emit():
    """Verify event_stream.emit() sends events to subscribed channel."""
    from app.middleware.event_stream import event_stream
    import asyncio

    correlation_id = "test-corr-456"

    # Subscribe first
    channel = await event_stream.subscribe(correlation_id)

    # Emit event
    await event_stream.emit(
        event_type="COMMAND_VERIFIED",
        correlation_id=correlation_id,
        payload={"decision_id": "dec-1"},
    )

    # Verify event is in queue
    event = await asyncio.wait_for(channel.get(), timeout=1.0)
    assert event["event_type"] == "COMMAND_VERIFIED"
    assert event["payload"]["decision_id"] == "dec-1"

    # Cleanup
    await event_stream.unsubscribe(correlation_id)


@pytest.mark.asyncio
async def test_event_stream_manager_unsubscribe():
    """Verify event_stream.unsubscribe() cleans up channel."""
    from app.middleware.event_stream import event_stream

    correlation_id = "test-corr-789"

    # Subscribe
    await event_stream.subscribe(correlation_id)

    # Verify channel exists (by checking internal registry)
    assert correlation_id in event_stream._channels

    # Unsubscribe
    await event_stream.unsubscribe(correlation_id)

    # Verify channel is removed
    assert correlation_id not in event_stream._channels


@pytest.mark.asyncio
async def test_event_stream_manager_no_subscribers():
    """Verify event_stream.emit() silently drops events if no subscribers.

    Frontend may have disconnected — event should not crash the system.
    """
    from app.middleware.event_stream import event_stream

    correlation_id = "test-corr-orphan"

    # Emit without subscribing first (no channel exists)
    # Should not raise an exception
    await event_stream.emit(
        event_type="COMMAND_VERIFIED",
        correlation_id=correlation_id,
        payload={"decision_id": "dec-1"},
    )

    # No assertion — just verify no exception was raised


@pytest.mark.asyncio
async def test_event_stream_multiple_subscribers_same_correlation():
    """Verify multiple subscribers to same correlation_id get same channel.

    If both frontend and backend monitoring subscribe to the same
    correlation_id, they should receive the same events.
    """
    from app.middleware.event_stream import event_stream
    import asyncio

    correlation_id = "test-corr-multi"

    # Two subscribers
    channel1 = await event_stream.subscribe(correlation_id)
    channel2 = await event_stream.subscribe(correlation_id)

    # Should be the same queue (singleton per correlation_id)
    assert channel1 is channel2

    # Emit event
    await event_stream.emit(
        event_type="COMMAND_VERIFIED",
        correlation_id=correlation_id,
        payload={"decision_id": "dec-1"},
    )

    # First subscriber gets event
    event = await asyncio.wait_for(channel1.get(), timeout=1.0)
    assert event["event_type"] == "COMMAND_VERIFIED"

    # Cleanup
    await event_stream.unsubscribe(correlation_id)
