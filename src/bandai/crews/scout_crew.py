from __future__ import annotations

import logging

from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.agents.agent_builder.base_agent import BaseAgent  # type: ignore

from bandai.config import (
    BANDI_PORTALS,
    PORTAL_WEIGHTS,
    _DEFAULT_PORTAL_WEIGHT,
    get_llm,
    get_embedder,
    get_memory,
)
from bandai.guardrails import validate_json_array
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import ResolvedContract, load_company_profile
from bandai.tools.crawler_tools import ContractDetailTool, TenderCrawlerTool
from bandai.utils import load_yaml_config

log = logging.getLogger(__name__)


def _build_weight_table() -> str:
    """Build a human-readable weight table for the resolution prompt."""
    rows = [f"   {name:<22} -> {w:.2f}" for name, w in sorted(PORTAL_WEIGHTS.items(), key=lambda x: -x[1])]
    rows.append(f"   {'(other portals)':<22} -> {_DEFAULT_PORTAL_WEIGHT:.2f}")
    return "\n".join(rows)


class ScoutCrew:
    """
    Scout Crew - discovers and deduplicates Italian public tenders.

    Because the number of crawler agents is dynamic (one per portal),
    we build agents and tasks programmatically.  The hierarchical
    process enables true parallel crawling of all portals.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    def build(self, user_preferences: str) -> tuple[Crew, Task]:
        """Build and return (crew_instance, preference_filter_task)."""
        ac = load_yaml_config("agents_scout.yaml")
        tc = load_yaml_config("tasks_scout.yaml")

        # Load company profile once (cached by @lru_cache).
        company = load_company_profile()
        ateco_codes_str = ", ".join(company.ateco_codes)

        # Crawler agents + tasks (one per portal, all async)
        crawler_agents: list[Agent] = []
        crawl_tasks: list[Task] = []

        for portal in BANDI_PORTALS:
            agent_cfg = ac["crawler_agent"]
            task_cfg = tc["crawl_task"]

            ag = Agent(
                role=agent_cfg["role"].format(portal_name=portal.name),
                goal=agent_cfg["goal"].format(
                    portal_name=portal.name,
                    portal_url=portal.base_url,
                ),
                backstory=agent_cfg["backstory"].format(portal_name=portal.name),
                tools=[TenderCrawlerTool(), ContractDetailTool()],
                llm=get_llm(fast=True),
                verbose=True,
                max_iter=5,
                max_retry_limit=2,
                respect_context_window=True,
                allow_delegation=True,
            )

            t = Task(
                description=task_cfg["description"].format(
                    portal_name=portal.name,
                    portal_url=portal.base_url,
                    ateco_codes=ateco_codes_str,
                ),
                expected_output=task_cfg["expected_output"],
                agent=ag,
                async_execution=True,
            )

            crawler_agents.append(ag)
            crawl_tasks.append(t)

        # Resolution Agent - deduplicates and ranks results
        res_cfg = ac["resolution_agent"]
        res_task_cfg = tc["resolution_task"]

        resolution_agent = Agent(
            role=res_cfg["role"],
            goal=res_cfg["goal"],
            backstory=res_cfg["backstory"],
            tools=[ContractDetailTool()],
            llm=get_llm(fast=False),
            verbose=True,
            max_iter=8,
            max_retry_limit=2,
            respect_context_window=True,
            inject_date=True,  # temporal awareness for deadline handling
            allow_delegation=True,
        )

        resolution_task = Task(
            description=res_task_cfg["description"].format(
                portal_weight_table=_build_weight_table(),
            ),
            expected_output=res_task_cfg["expected_output"],
            agent=resolution_agent,
            context=crawl_tasks,
            output_pydantic=list[ResolvedContract],
            guardrail=validate_json_array,
            guardrail_max_retries=3,
        )

        # Preference Filter Agent - applies user preferences
        preference_cfg = ac["preference_filter_agent"]
        preference_task_cfg = tc["preference_filter_task"]

        preference_filter_agent = Agent(
            role=preference_cfg["role"],
            goal=preference_cfg["goal"],
            backstory=preference_cfg["backstory"],
            llm=get_llm(fast=False),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
            allow_delegation=True,
        )

        preference_filter_task = Task(
            description=preference_task_cfg["description"].format(
                user_preferences=user_preferences,
            ),
            expected_output=preference_task_cfg["expected_output"],
            agent=preference_filter_agent,
            context=[resolution_task],
            output_pydantic=list[ResolvedContract],
            guardrail=lambda r: validate_json_array(r, strip_fences=True),
            guardrail_max_retries=3,
        )

        all_agents = crawler_agents + [resolution_agent, preference_filter_agent]
        all_tasks = crawl_tasks + [resolution_task, preference_filter_task]

        agent_roster = "\n".join(f"  - {a.role}" for a in all_agents)
        mgr_instructions = (
            "You are the Crew Manager. Delegate work to your agents by "
            "calling delegate_work_to_coworker with the EXACT agent role name "
            "from the list below. Do NOT abbreviate, paraphrase, or invent "
            "names. Use them verbatim:\n\n"
            f"Available agents:\n{agent_roster}\n\n"
            "Each task is already assigned to a specific agent. Your job is "
            "to orchestrate execution order and re-delegate only when needed. "
            "When you delegate, always pass the EXACT role string as the "
            "coworker parameter."
        )

        built_crew = Crew(
            agents=all_agents,
            tasks=all_tasks,
            process=Process.hierarchical,
            manager_llm=get_llm(fast=True),
            manager_instructions=mgr_instructions,
            verbose=True,
            memory=get_memory(),
            knowledge_sources=get_all_knowledge_sources(),
            embedder=get_embedder(),
        )

        return built_crew, preference_filter_task
