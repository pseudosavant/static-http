"""Cross-platform keyboard watcher for ``q`` / ``Q`` shutdown."""

from __future__ import annotations

import sys
import threading


def start_quit_watcher(on_quit) -> tuple[threading.Event, bool]:
    """Start monitoring for a single-key quit command.

    Returns:
        A tuple of ``(stop_event, needs_enter_confirmation)``.
    """

    stop_event = threading.Event()

    # Windows single-key path.
    try:
        import msvcrt  # type: ignore[import-not-found]

        def _watch() -> None:
            while not stop_event.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    if ch.lower() == "q":
                        if not stop_event.is_set():
                            stop_event.set()
                            on_quit()
                if stop_event.wait(0.1):
                    return

        thread = threading.Thread(target=_watch, name="http-here-keyboard", daemon=True)
        thread.start()
        return stop_event, False
    except Exception:
        pass

    # POSIX raw terminal path.
    try:
        import os
        import select
        import termios
        import tty

        if not sys.stdin.isatty():
            raise RuntimeError("stdin is not a tty")

        def _watch() -> None:
            fd = sys.stdin.fileno()
            old = termios.tcgetattr(fd)
            try:
                tty.setraw(fd)
                while not stop_event.is_set():
                    ready, _, _ = select.select([fd], [], [], 0.1)
                    if not ready:
                        continue
                    ch = os.read(fd, 1).decode(errors="ignore")
                    if ch.lower() == "q":
                        stop_event.set()
                        on_quit()
            finally:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
                except Exception:
                    pass

        thread = threading.Thread(target=_watch, name="http-here-keyboard", daemon=True)
        thread.start()
        return stop_event, False
    except Exception:
        pass

    # Fallback path input mode.
    def _watch() -> None:
        for line in sys.stdin:
            if stop_event.is_set():
                return
            if line.strip().lower() == "q":
                stop_event.set()
                on_quit()
                return

    thread = threading.Thread(target=_watch, name="http-here-keyboard", daemon=True)
    thread.start()
    return stop_event, True
