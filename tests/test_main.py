"""
tests/test_main.py - Tests for main-process helpers.
"""

import signal

from main import temporarily_ignore_sigint


def test_temporarily_ignore_sigint_restores_previous_handler():
    """The SIGINT handler should be restored after the critical section."""
    previous_handler = signal.getsignal(signal.SIGINT)

    try:
        signal.signal(signal.SIGINT, signal.default_int_handler)

        with temporarily_ignore_sigint():
            assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN

        assert signal.getsignal(signal.SIGINT) == signal.default_int_handler
    finally:
        signal.signal(signal.SIGINT, previous_handler)
