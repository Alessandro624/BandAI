from __future__ import annotations

import logging
from pathlib import Path

import yaml
from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.project import CrewBase, crew  # type: ignore
from crewai.agents.agent_builder.base_agent import BaseAgent  # type: ignore

from bandai.config import get_llm
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import (
    AuctionResult,
    CompanyProfile,
    DepartmentBid,
    DepartmentProfile,
    FinalProposal,
    load_company_profile,
)
from bandai.tools.crawler_tools import ProposalWriterTool

log = logging.getLogger(__name__)

_CFG = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((_CFG / filename).read_text(encoding="utf-8"))


def _load_company() -> CompanyProfile:
    """Load and cache the company profile from knowledge/."""
    return load_company_profile()


# Crew Class


@CrewBase
class ProposalCrew:
    """
    Proposal Crew - runs an auction to build the optimal tender proposal.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents_proposal.yaml"
    tasks_config = "config/tasks_proposal.yaml"

    def build(
        self,
        contract_summary: str,
        total_word_limit: int = 3000,
    ) -> tuple[Crew, Task]:
        """Build and return (crew, proposal_task) for a specific contract."""
        ac = _load_yaml("agents_proposal.yaml")
        tc = _load_yaml("tasks_proposal.yaml")

        dept_agents: list[Agent] = []
        dept_bid_tasks: list[Task] = []

        company = _load_company()

        for dept_name, dept_profile in company.departments.items():
            profile_str = (
                f"Certifications: {dept_profile.certifications}\n"
                f"Capabilities  : {dept_profile.capabilities}\n"
                f"Case studies  : {dept_profile.case_studies or ['None yet']}\n"
                f"KPIs          : {dept_profile.kpis}"
            )

            ag = Agent(
                role=ac["department_rep"]["role"].format(dept_name=dept_name),
                goal=ac["department_rep"]["goal"].format(dept_name=dept_name),
                backstory=ac["department_rep"]["backstory"].format(
                    dept_name=dept_name,
                    company_name=company.name,
                    dept_profile=profile_str,
                ),
                llm=get_llm(fast=True),
                verbose=True,
                max_retry_limit=2,
                respect_context_window=True,
            )

            t = Task(
                description=tc["dept_bid_task"]["description"].format(
                    dept_name=dept_name,
                    contract_summary=contract_summary,
                ),
                expected_output=tc["dept_bid_task"]["expected_output"],
                agent=ag,
                output_pydantic=DepartmentBid,
                async_execution=True,
            )

            dept_agents.append(ag)
            dept_bid_tasks.append(t)

        # Auctioneer evaluates bids
        auctioneer = Agent(
            role=ac["auctioneer"]["role"],
            goal=ac["auctioneer"]["goal"],
            backstory=ac["auctioneer"]["backstory"],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
            reasoning=True,  # complex scoring and word budget allocation
        )
        auction_task = Task(
            description=tc["auction_task"]["description"].format(
                contract_summary=contract_summary,
                total_word_limit=total_word_limit,
            ),
            expected_output=tc["auction_task"]["expected_output"],
            agent=auctioneer,
            context=dept_bid_tasks,
            output_pydantic=AuctionResult,
        )

        # Proposal Architect writes the final document
        architect = Agent(
            role=ac["proposal_architect"]["role"],
            goal=ac["proposal_architect"]["goal"],
            backstory=ac["proposal_architect"]["backstory"],
            tools=[ProposalWriterTool()],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
        )
        proposal_task = Task(
            description=tc["proposal_task"]["description"].format(
                contract_summary=contract_summary,
                company_name=_load_company().name,
            ),
            expected_output=tc["proposal_task"]["expected_output"],
            agent=architect,
            context=[auction_task],
            output_pydantic=FinalProposal,
        )

        all_agents = dept_agents + [auctioneer, architect]
        all_tasks = dept_bid_tasks + [auction_task, proposal_task]

        built_crew = Crew(
            agents=all_agents,
            tasks=all_tasks,
            process=Process.sequential,
            verbose=True,
            memory=True,
            knowledge_sources=get_all_knowledge_sources(),
        )
        return built_crew, proposal_task

    @crew
    def crew(self) -> Crew:
        """Creates the Proposal Crew."""
        return self.build(contract_summary="")[0]
