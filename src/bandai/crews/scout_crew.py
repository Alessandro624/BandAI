from __future__ import annotations

import yaml
from pathlib import Path
from crewai import Agent, Crew, Process, Task  # type: ignore

from bandai.config import BANDI_PORTALS, COMPANY, get_llm, PORTAL_WEIGHTS, _DEFAULT_PORTAL_WEIGHT
from bandai.models import ResolvedContract
from bandai.tools.crawler_tools import ContractDetailTool, TenderCrawlerTool

_CFG = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((_CFG / filename).read_text(encoding="utf-8"))


def _build_weight_table() -> str:
    rows = [f"   {name:<22} → {w:.2f}" for name, w in sorted(PORTAL_WEIGHTS.items(), key=lambda x: -x[1])]
    rows.append(f"   {'(other portals)':<22} -> {_DEFAULT_PORTAL_WEIGHT:.2f}")
    return "\n".join(rows)


class ScoutCrew:
    """
    Scout Crew - discovers and deduplicates Italian public tenders.

    Because the number of crawler agents is dynamic (one per portal),
    we build agents and tasks programmatically rather than using the
    @agent / @task decorators (which expect a fixed set of methods).
    The @crew decorator is still used for the final assembly.
    """

    def build(self, user_preferences: str) -> tuple["ScoutCrew", Task]:
        """
        Build and return (crew_instance, resolution_task).
        Call crew_instance.crew().kickoff() to run.
        """
        # Crawler agents + tasks (one per portal, all async)
        crawler_agents: list[Agent] = []
        crawl_tasks: list[Task] = []

        ac = _load_yaml("agents_scout.yaml")
        tc = _load_yaml("tasks_scout.yaml")

        for portal in BANDI_PORTALS:
            agent_cfg = ac["crawler_agent"]
            task_cfg = tc["crawl_task"]

            ag = Agent(
                role=agent_cfg["role"].format(portal_name=portal["name"]),
                goal=agent_cfg["goal"].format(
                    portal_name=portal["name"],
                    portal_url=portal["base_url"],
                ),
                backstory=agent_cfg["backstory"].format(portal_name=portal["name"]),
                tools=[TenderCrawlerTool(), ContractDetailTool()],
                llm=get_llm(fast=True),  # cheap model for crawlers
                verbose=True,
                max_iter=5,
            )

            t = Task(
                description=task_cfg["description"].format(
                    portal_name=portal["name"],
                    portal_url=portal["base_url"],
                    ateco_codes=", ".join(COMPANY.ateco_codes),
                ),
                expected_output=task_cfg["expected_output"],
                agent=ag,
                async_execution=True,  # all crawlers run in parallel
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
            llm=get_llm(fast=False),  # main model for reasoning
            verbose=True,
            max_iter=8,
        )

        resolution_task = Task(
            description=res_task_cfg["description"].format(
                portal_weight_table=_build_weight_table(),
            ),
            expected_output=res_task_cfg["expected_output"],
            agent=resolution_agent,
            context=crawl_tasks,  # waits for all async crawlers
            output_pydantic=list[ResolvedContract],
        )

        preference_cfg = ac["preference_filter_agent"]
        preference_task_cfg = tc["preference_filter_task"]

        preference_filter_agent = Agent(
            role=preference_cfg["role"],
            goal=preference_cfg["goal"],
            backstory=preference_cfg["backstory"],
            llm=get_llm(fast=False),
        )

        preference_filter_task = Task(
            description=preference_task_cfg["description"].format(
                user_preferences=user_preferences,
            ),
            expected_output=preference_task_cfg["expected_output"],
            agent=preference_filter_agent,
            context=[resolution_task],
            human_input=True,  # pauses here, shows draft, waits for human
            pydantic_output=list[ResolvedContract],
        )

        all_agents = crawler_agents + [resolution_agent, preference_filter_agent]
        all_tasks = crawl_tasks + [resolution_task, preference_filter_task]

        built_crew = Crew(
            agents=all_agents,
            tasks=all_tasks,
            process=Process.sequential,
            verbose=True,
        )
        return built_crew, resolution_task
