"""Bounded request framing and liveness for the two TimesFM process boundaries."""
import os
import threading
import time


def read_request_line(fd, limit):
    data = bytearray()
    while True:
        newline = data.find(b"\n")
        if newline >= 0:
            return bytes(data[:newline]), bytes(data[newline+1:])
        if len(data) > limit:
            break
        block = os.read(fd, min(65536, limit + 1 - len(data)))
        if not block:
            break
        data.extend(block)
    return bytes(data), b""


def watch_owner(fd, pending, lost):
    # Use the raw FD so a blocked daemon thread cannot hold Python's stdin lock.
    last = [time.monotonic()]
    stopped = threading.Event()

    def read_heartbeats():
        buffered = pending
        try:
            while not stopped.is_set():
                while b"\n" in buffered:
                    line, buffered = buffered.split(b"\n", 1)
                    if line != b".":
                        return
                    last[0] = time.monotonic()
                if len(buffered) > 1:
                    return
                block = os.read(fd, 4096)
                if not block:
                    return
                buffered += block
        except OSError:
            pass
        finally:
            stopped.set()

    def watchdog():
        while not stopped.wait(.5) and time.monotonic() - last[0] < 5:
            pass
        lost()

    threading.Thread(target=read_heartbeats, daemon=True).start()
    threading.Thread(target=watchdog, daemon=True).start()
