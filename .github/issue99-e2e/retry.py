"""Synthetic retry decision used only by the Issue #99 automation exercise."""


def may_retry(status):
    """Retry only when the operation is known not to have started."""
    return status in {"not_started", "unknown"}
