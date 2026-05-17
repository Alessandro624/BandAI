from __future__ import annotations

import logging
import json

from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.agents.agent_builder.base_agent import BaseAgent  # type: ignore
from crewai import TaskOutput  # type: ignore

from bandai.config import BANDI_PORTALS, get_llm, get_embedder, get_memory, PORTAL_WEIGHTS, _DEFAULT_PORTAL_WEIGHT
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import ResolvedContract, load_company_profile
from bandai.tools.crawler_tools import ContractDetailTool, TenderCrawlerTool
from bandai.crews.utils import load_yaml_config

log = logging.getLogger(__name__)


def _build_weight_table() -> str:
    rows = [f"   {name:<22} -> {w:.2f}" for name, w in sorted(PORTAL_WEIGHTS.items(), key=lambda x: -x[1])]
    rows.append(f"   {'(other portals)':<22} -> {_DEFAULT_PORTAL_WEIGHT:.2f}")
    return "\n".join(rows)


# Guardrail: validate that resolution output is a JSON array


def _validate_resolution_output(result: TaskOutput):
    """Ensure the resolution agent returns a parseable JSON array."""
    raw = result.raw.strip()

    # Try to find JSON array bounds in the text (handles markdown and explanations)
    start_idx = raw.find("[")
    end_idx = raw.rfind("]")

    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        return (False, "No JSON array found in response. Ensure output contains '[...]'.")

    json_str = raw[start_idx : end_idx + 1]

    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            return (False, "Output must be a JSON array (list), not a single object.")
        return (True, json_str)
    except json.JSONDecodeError as e:
        return (False, f"Extracted text is not valid JSON: {str(e)}. Ensure the array is properly formatted.")


def _validate_preference_output(result: TaskOutput):
    """Ensure the preference filter returns a valid JSON array."""
    raw = result.raw.strip()

    # Try to find JSON array bounds in the text (handles markdown and explanations)
    start_idx = raw.find("[")
    end_idx = raw.rfind("]")

    if start_idx == -1 or end_idx == -1 or start_idx >= end_idx:
        return (False, "No JSON array found in response. Ensure output contains '[...]'.")

    json_str = raw[start_idx : end_idx + 1]

    try:
        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            return (False, "Output must be a JSON array (list).")
        return (True, json_str)
    except json.JSONDecodeError as e:
        return (False, f"Extracted text is not valid JSON: {str(e)}. Return a properly formatted JSON array only.")


# Crew Class


class ScoutCrew:
    """
    Scout Crew - discovers and deduplicates Italian public tenders.

    Because the number of crawler agents is dynamic (one per portal),
    we build agents and tasks programmatically rather than using the
    @agent / @task decorators for the dynamic parts. The @crew
    decorator is used for the final assembly.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    def build(self, user_preferences: str) -> tuple[Crew, Task]:
        """Build and return (crew_instance, preference_filter_task)."""
        # Crawler agents + tasks (one per portal, all async)
        crawler_agents: list[Agent] = []
        crawl_tasks: list[Task] = []

        ac = load_yaml_config("agents_scout.yaml")
        tc = load_yaml_config("tasks_scout.yaml")

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
            )

            t = Task(
                description=task_cfg["description"].format(
                    portal_name=portal.name,
                    portal_url=portal.base_url,
                    ateco_codes=", ".join(load_company_profile().ateco_codes),
                ),
                expected_output=task_cfg["expected_output"],
                agent=ag,
                async_execution=True,
            )

            crawler_agents.append(ag)
            crawl_tasks.append(t)

        # Resolution Agent + task
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
        )

        resolution_task = Task(
            description=res_task_cfg["description"].format(
                portal_weight_table=_build_weight_table(),
            ),
            expected_output=res_task_cfg["expected_output"],
            agent=resolution_agent,
            context=crawl_tasks,
            output_pydantic=list[ResolvedContract],
            guardrail=_validate_resolution_output,
            guardrail_max_retries=3,
        )

        # Preference Filter Agent + task
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
        )

        preference_filter_task = Task(
            description=preference_task_cfg["description"].format(
                user_preferences=user_preferences,
            ),
            expected_output=preference_task_cfg["expected_output"],
            agent=preference_filter_agent,
            context=[resolution_task],
            human_input=True,
            output_pydantic=list[ResolvedContract],
            guardrail=_validate_preference_output,
            guardrail_max_retries=3,
        )

        all_agents = crawler_agents + [resolution_agent, preference_filter_agent]
        all_tasks = crawl_tasks + [resolution_task, preference_filter_task]

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
