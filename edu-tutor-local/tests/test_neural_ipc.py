"""CPU-only IPC shutdown/backlog checks; no model or CUDA execution."""
import io
import queue
import threading

from edu_tutor.models.runtime import _read_pipe


def test_bounded_pipe_reader_stops_without_waiting_for_slow_consumer():
    events = queue.Queue(maxsize=2)
    stopped = threading.Event()
    source = io.StringIO("event\n" * 10000)
    reader = threading.Thread(target=_read_pipe, args=(source, events, stopped))
    reader.start()
    assert events.get(timeout=1) == "event\n"
    stopped.set()
    reader.join(timeout=1)
    assert not reader.is_alive()
    assert events.qsize() <= 2


def test_pipe_preserves_order_and_terminal_sentinel():
    events = queue.Queue(maxsize=2)
    stopped = threading.Event()
    source = io.StringIO('first\nsecond\nthird\n')
    reader = threading.Thread(target=_read_pipe, args=(source, events, stopped))
    reader.start()
    assert [events.get(timeout=1) for _ in range(4)] == ['first\n', 'second\n', 'third\n', None]
    reader.join(timeout=1)
    assert not reader.is_alive()
