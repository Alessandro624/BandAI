from __future__ import annotations

import logging

from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.agents.agent_builder.base_agent import BaseAgent  # type: ignore

from bandai.config import get_llm, get_embedder, get_memory
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import (
    AuctionResult,
    CompanyProfile,
    DepartmentBid,
    FinalProposal,
    load_company_profile,
)
from bandai.tools.crawler_tools import ProposalWriterTool
from bandai.utils import load_yaml_config

log = logging.getLogger(__name__)

# Maximum number of departments that will be given their own agent.
# Beyond this limit, the proposal crew becomes unwieldy and may hit
# LLM rate limits or context window constraints.
MAX_DEPARTMENTS = 15


class ProposalCrew:
    """
    Proposal Crew - runs an auction to build the optimal tender proposal.

    Department representative agents submit bids concurrently (via
    async_execution=True), the auctioneer scores and selects
    winners, and the proposal architect writes the final document.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    def build(
        self,
        contract_summary: str,
        total_word_limit: int = 3000,
    ) -> tuple[Crew, Task]:
        """Build and return (crew, proposal_task) for a specific contract."""
        ac = load_yaml_config("agents_proposal.yaml")
        tc = load_yaml_config("tasks_proposal.yaml")

        # Load company profile once (cached by @lru_cache).
        company = load_company_profile()

        # Guard against excessive department counts.
        dept_items = list(company.departments.items())
        if len(dept_items) > MAX_DEPARTMENTS:
            log.warning(
                "Company has %d departments but max is %d. " "Only the first %d will participate in the auction.",
                len(dept_items),
                MAX_DEPARTMENTS,
                MAX_DEPARTMENTS,
            )
            dept_items = dept_items[:MAX_DEPARTMENTS]

        dept_agents: list[Agent] = []
        dept_bid_tasks: list[Task] = []

        for dept_name, dept_profile in dept_items:
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
                company_name=company.name,
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
            process=Process.hierarchical,
            manager_llm=get_llm(fast=True),
            verbose=True,
            memory=get_memory(),
            knowledge_sources=get_all_knowledge_sources(),
            embedder=get_embedder(),
        )
        return built_crew, proposal_task
