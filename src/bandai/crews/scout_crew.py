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
from bandai.guardrails import (
    validate_json_array,
    validate_resolved_contract_array,
    validate_tender_info_array,
)
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import ResolvedContract
from bandai.tools.crawler_tools import TendersOverviewExtractorTool, SinglePageLoaderTool
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
    we build agents and tasks programmatically. Crawler tasks are marked
    async to allow concurrent discovery when supported by the runtime.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    tenders_count_per_portal: int = 3

    def build(self, user_preferences: str) -> tuple[Crew, Task]:
        """Build and return (crew_instance, preference_filter_task)."""
        ac = load_yaml_config("agents_scout.yaml")
        tc = load_yaml_config("tasks_scout.yaml")

        # Load company profile once (cached by @lru_cache).
        # company = load_company_profile()
        # ateco_codes_str = ", ".join(company.ateco_codes)

        # Crawler agents + tasks
        # For each portal: Discovery + Extraction (all async)
        disc_agents: list[Agent] = []
        disc_tasks: list[Task] = []

        extr_agents: list[Agent] = []
        extr_tasks: list[Task] = []

        for portal in BANDI_PORTALS:
            disc_agent_cfg = ac["discovery_agent"]
            disc_task_cfg = tc["discovery_task"]

            disc_ag = Agent(
                role=disc_agent_cfg["role"],
                goal=disc_agent_cfg["goal"].format(portal=portal.name),
                backstory=disc_agent_cfg["backstory"],
                tools=[TendersOverviewExtractorTool()],
                llm=get_llm(fast=True),
                verbose=True,
                max_iter=5,
                max_retry_limit=2,
                respect_context_window=True,
                allow_delegation=False,
            )

            disc_t = Task(
                description=disc_task_cfg["description"].format(
                    portal_name=portal.name,
                    tenders_count=self.tenders_count_per_portal,
                ),
                expected_output=disc_task_cfg["expected_output"],
                agent=disc_ag,
                async_execution=True,
                # output_pydantic = list[TenderOverview],
                guardrail=lambda r: validate_json_array(r, strip_fences=True),
                guardrail_max_retries=3,
            )

            disc_agents.append(disc_ag)
            disc_tasks.append(disc_t)

            extr_agent_cfg = ac["extraction_agent"]
            extr_task_cfg = tc["extraction_task"]

            extr_ag = Agent(
                role=extr_agent_cfg["role"],
                goal=extr_agent_cfg["goal"].format(portal_name=portal.name),
                backstory=extr_agent_cfg["backstory"],
                tools=[SinglePageLoaderTool()],
                llm=get_llm(fast=True),
                verbose=True,
                max_iter=self.tenders_count_per_portal * 2 + 2,
                max_retry_limit=2,
                respect_context_window=True,
                allow_delegation=False,
            )

            extr_t = Task(
                description=extr_task_cfg["description"].format(
                    portal_name=portal.name,
                    tenders_count=self.tenders_count_per_portal,
                ),
                expected_output=extr_task_cfg["expected_output"],
                context=[disc_t],
                agent=extr_ag,
                async_execution=False,
                # output_pydantic = list[TenderOverview],
                guardrail=lambda r: validate_tender_info_array(r, strip_fences=True),
                guardrail_max_retries=3,
            )

            extr_agents.append(extr_ag)
            extr_tasks.append(extr_t)

        # Resolution Agent - deduplicates and ranks results
        res_cfg = ac["resolution_agent"]
        res_task_cfg = tc["resolution_task"]

        resolution_agent = Agent(
            role=res_cfg["role"],
            goal=res_cfg["goal"],
            backstory=res_cfg["backstory"],
            llm=get_llm(fast=False),
            verbose=True,
            max_iter=8,
            max_retry_limit=2,
            respect_context_window=True,
            inject_date=True,  # temporal awareness for deadline handling
            allow_delegation=False,
        )

        resolution_task = Task(
            description=res_task_cfg["description"].format(
                portal_weight_table=_build_weight_table(),
            ),
            expected_output=res_task_cfg["expected_output"],
            agent=resolution_agent,
            context=extr_tasks,
            output_pydantic=list[ResolvedContract],
            guardrail=validate_resolved_contract_array,
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
            allow_delegation=False,
        )

        preference_filter_task = Task(
            description=preference_task_cfg["description"].format(
                user_preferences=user_preferences,
            ),
            expected_output=preference_task_cfg["expected_output"],
            agent=preference_filter_agent,
            context=[resolution_task],
            output_pydantic=list[ResolvedContract],
            guardrail=lambda r: validate_resolved_contract_array(r, strip_fences=True),
            guardrail_max_retries=3,
        )

        all_agents = disc_agents + extr_agents + [resolution_agent, preference_filter_agent]
        all_tasks = disc_tasks + extr_tasks + [resolution_task, preference_filter_task]

        built_crew = Crew(
            agents=all_agents,
            tasks=all_tasks,
            process=Process.sequential,
            verbose=True,
            memory=get_memory(),
            knowledge_sources=get_all_knowledge_sources(),
            embedder=get_embedder(),
        )

        return built_crew, preference_filter_task
