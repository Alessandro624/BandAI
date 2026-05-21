from __future__ import annotations

import os

# LLM Memory Factory


def get_memory() -> "Memory | bool":  # type: ignore[valid-type]:
    """
    Return a CrewAI Memory object wired to the active provider.

    Memory objects are intentionally not cached: each crew should
    receive its own independent Memory instance so that context
    isolation is preserved across pipeline phases.
    """
    if os.getenv("DISABLE_MEMORY", "false").lower() in ("1", "true", "yes"):
        return False  # type: ignore[return-value]

    from crewai.memory.unified_memory import Memory  # type: ignore

    from bandai.config.embedder import get_embedder  # noqa: E402
    from bandai.config.llm import get_llm  # noqa: E402

    # Memory uses the fast model for its analysis LLM (scope inference,
    # importance scoring, consolidation).  The model ID must match
    # whatever the active provider expects.
    memory_llm = get_llm(fast=True)

    return Memory(
        llm=memory_llm,
        embedder=get_embedder(),
    )
