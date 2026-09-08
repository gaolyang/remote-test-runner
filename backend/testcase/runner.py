"""Test case runner facade.

The current MVP keeps orchestration in :class:`ExecutionEngine`; this alias leaves
a stable import point for future scheduling and multi-target runners.
"""

from backend.execution.engine import ExecutionEngine

TestCaseRunner = ExecutionEngine

