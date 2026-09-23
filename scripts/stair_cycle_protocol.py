"""Shared stop boundary for stair training and closed-loop evaluation."""

import torch


def stop_outcome(holding, elapsed_steps, drift_m, speed_m_s, *, hold_steps,
                 max_drift_m, max_speed_m_s):
    """Return due, success and failure at the first completed hold boundary.

    A caller must terminate a failed hold immediately. Once successful, it
    changes to the restart phase; neither outcome can be reconsidered later.
    """
    due = holding & (elapsed_steps >= hold_steps)
    good = due & (drift_m <= max_drift_m) & (speed_m_s <= max_speed_m_s)
    return due, good, due & ~good
