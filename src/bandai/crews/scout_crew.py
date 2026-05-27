from __future__ import annotations

from crewai import Agent, Crew, Process, Task  # type: ignore

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
from bandai.tools.crawler_tools import TendersOverviewExtractorTool, SinglePageLoaderTool
from bandai.utils import load_yaml_config


def _build_weight_table() -> str:
    """Build a human-readable weight table for the resolution prompt."""
    rows = [f"   {name:<22} -> {w:.2f}" for name, w in sorted(PORTAL_WEIGHTS.items(), key=lambda x: -x[1])]
    rows.append(f"   {'(other portals)':<22} -> {_DEFAULT_PORTAL_WEIGHT:.2f}")
    return "\n".join(rows)


def _validate_discovery_output(result):
    return validate_json_array(result, strip_fences=True)


def _validate_extraction_output(result):
    return validate_tender_info_array(result, strip_fences=True)


def _validate_resolved_output(result):
    return validate_resolved_contract_array(result, strip_fences=True)


class ScoutCrew:
    """
    Scout Crew - discovers and deduplicates Italian public tenders.

    Because the number of portals is dynamic, discovery and extraction agents
    are built programmatically from the portal configuration.
    """

    tenders_count_per_portal: int = 3

    def build(self, user_preferences: str) -> tuple[Crew, Task]:
        """Build and return (crew_instance, preference_filter_task)."""
        ac = load_yaml_config("agents_scout.yaml")
        tc = load_yaml_config("tasks_scout.yaml")
        portals_count = len(BANDI_PORTALS)

        all_agents: list[Agent] = []
        all_tasks: list[Task] = []
        extraction_tasks: list[Task] = []

        for portal in BANDI_PORTALS:
            discovery_agent_cfg = ac["discovery_agent"]
            discovery_task_cfg = tc["discovery_task"]

            discovery_agent = Agent(
                role=discovery_agent_cfg["role"],
                goal=discovery_agent_cfg["goal"].format(portal=portal.name),
                backstory=discovery_agent_cfg["backstory"],
                tools=[TendersOverviewExtractorTool()],
                llm=get_llm(fast=True),
                verbose=True,
                max_iter=5,
                max_retry_limit=2,
                respect_context_window=True,
                allow_delegation=False,
            )

            discovery_task = Task(
                description=discovery_task_cfg["description"].format(
                    portal_name=portal.name,
                    tenders_count=self.tenders_count_per_portal,
                ),
                expected_output=discovery_task_cfg["expected_output"],
                agent=discovery_agent,
                guardrail=_validate_discovery_output,
                guardrail_max_retries=3,
            )

            all_agents.append(discovery_agent)
            all_tasks.append(discovery_task)

            extraction_agent_cfg = ac["extraction_agent"]
            extraction_task_cfg = tc["extraction_task"]

            extraction_agent = Agent(
                role=extraction_agent_cfg["role"],
                goal=extraction_agent_cfg["goal"].format(portal_name=portal.name),
                backstory=extraction_agent_cfg["backstory"],
                tools=[SinglePageLoaderTool()],
                llm=get_llm(fast=True),
                verbose=True,
                max_iter=self.tenders_count_per_portal * 2 + 2,
                max_retry_limit=2,
                respect_context_window=True,
                allow_delegation=False,
            )

            extraction_task = Task(
                description=extraction_task_cfg["description"].format(
                    portal_name=portal.name,
                    tenders_count=self.tenders_count_per_portal,
                ),
                expected_output=extraction_task_cfg["expected_output"],
                context=[discovery_task],
                agent=extraction_agent,
                guardrail=_validate_extraction_output,
                guardrail_max_retries=3,
            )

            all_agents.append(extraction_agent)
            all_tasks.append(extraction_task)
            extraction_tasks.append(extraction_task)

        # Resolution Agent - deduplicates and ranks results
        res_cfg = ac["resolution_agent"]
        res_task_cfg = tc["resolution_task"]

        resolution_agent = Agent(
            role=res_cfg["role"],
            goal=res_cfg["goal"].format(portals_count=portals_count),
            backstory=res_cfg["backstory"],
            llm=get_llm(fast=False),
            verbose=True,
            max_iter=8,
            max_retry_limit=2,
            respect_context_window=True,
            inject_date=True,
            allow_delegation=False,
        )

        resolution_task = Task(
            description=res_task_cfg["description"].format(
                tenders_count=self.tenders_count_per_portal,
                portals_count=portals_count,
                portal_weight_table=_build_weight_table(),
            ),
            expected_output=res_task_cfg["expected_output"],
            agent=resolution_agent,
            context=extraction_tasks,
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
            guardrail=_validate_resolved_output,
            guardrail_max_retries=3,
        )

        all_agents.extend([resolution_agent, preference_filter_agent])
        all_tasks.extend([resolution_task, preference_filter_task])

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
