"""OpenAI Agents SDK integration with a deterministic local-tool boundary."""

from .agent import AgentRunResult, build_agent, run_agent
from .instructions import SYSTEM_INSTRUCTIONS

__all__ = ["AgentRunResult", "SYSTEM_INSTRUCTIONS", "build_agent", "run_agent"]
