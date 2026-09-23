"""Learned-movement toolkit: record real human input for training models.

``humanpc trainer`` opens a fullscreen app that prompts you through movement
tasks (point-to-point, clicks, drags, scrolls, tracing, reading, chains) while a
low-level hook records the raw hardware event stream. Sessions are stored as
compact, delta-encoded ``.npz`` files plus a JSON sidecar describing each task.

Requires the ``learn`` extra (numpy) for storage.
"""

from .tasks import DEFAULT_WEIGHTS, KINDS, Task, TaskSampler

__all__ = ["DEFAULT_WEIGHTS", "KINDS", "Task", "TaskSampler"]
