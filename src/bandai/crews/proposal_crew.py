from __future__ import annotations

import yaml
from pathlib import Path
from crewai import Agent, Crew, Process, Task  # type: ignore[import]
from crewai.project import CrewBase  # type: ignore[import]

from bandai.config import COMPANY, get_llm
from bandai.models import AuctionResult, DepartmentBid, FinalProposal
from bandai.tools.crawler_tools import ProposalWriterTool

_CFG = Path(__file__).parent.parent / "config"

# TODO: inject from company knowledge base instead of hardcoding here
DEPARTMENT_PROFILES: dict[str, dict] = {
    "Cloud Infrastructure": {
        "capabilities": [
            "Design and management of multi-cloud environments (AWS, Azure, GCP)",
            "AgID-qualified cloud migration for Italian PA",
            "99.99% SLA on managed infrastructure services",
        ],
        "certifications": ["ISO 20000-1:2018", "AgID Qualificazione Cloud (IaaS/PaaS)"],
        "case_studies": [
            "Migrazione documentale Comune di Cagliari (2022) - €180k, zero downtime",
        ],
        "kpis": {"uptime_sla": "99.99%", "avg_migration_weeks": 8},
    },
    "Cybersecurity": {
        "capabilities": [
            "VAPT (Vulnerability Assessment & Penetration Testing)",
            "DPO as a Service (GDPR)",
            "SOC 24/7 with SIEM integration",
            "NIS2 compliance gap analysis",
        ],
        "certifications": ["ISO 27001:2022", "CEH", "OSCP"],
        "case_studies": [
            "GDPR remediation ASL Ogliastra (2023) – €95k, 0 audit findings",
        ],
        "kpis": {"mttd_minutes": 12, "mttr_hours": 2.5},
    },
    "Software Development": {
        "capabilities": [
            "Agile/Scrum delivery (2-week sprints)",
            "Full-stack web & mobile (React, FastAPI, Flutter)",
            "PA interoperability via ModI / PDND",
        ],
        "certifications": ["ISO 9001:2015", "AWS Certified Developer"],
        "case_studies": [],
        "kpis": {"defect_rate_percent": 0.8, "on_time_delivery_percent": 94},
    },
    "Customer Support & SLA Management": {
        "capabilities": [
            "Multi-channel helpdesk (phone, email, chat, ticket)",
            "SLA-driven escalation with guaranteed response times",
            "Italian-language L1/L2/L3 support",
        ],
        "certifications": ["ISO 20000-1:2018", "ITIL 4 Foundation"],
        "case_studies": [],
        "kpis": {"first_contact_resolution_percent": 78, "csat_score": 4.6},
    },
    "Project Management Office": {
        "capabilities": [
            "PMP-certified project managers",
            "Full MS Project + Jira tracking",
            "Risk register and steering committee reporting",
        ],
        "certifications": ["PMP", "PRINCE2 Practitioner"],
        "case_studies": [],
        "kpis": {"budget_variance_percent": 3.2, "schedule_variance_percent": 4.1},
    },
}


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((_CFG / filename).read_text(encoding="utf-8"))


@CrewBase
class ProposalCrew:
    """Proposal Crew - runs an auction to build the optimal tender proposal."""

    def build(
        self,
        contract_summary: str,
        total_word_limit: int = 3000,
    ) -> tuple[Crew, Task]:
        """
        Build and return (crew, proposal_task) for a specific contract.
        proposal_task.output.pydantic is a FinalProposal.
        """
        ac = _load_yaml("agents_proposal.yaml")
        tc = _load_yaml("tasks_proposal.yaml")

        dept_agents: list[Agent] = []
        dept_bid_tasks: list[Task] = []

        for dept_name, profile in DEPARTMENT_PROFILES.items():
            profile_str = (
                f"Certifications: {profile['certifications']}\n"
                f"Capabilities  : {profile['capabilities']}\n"
                f"Case studies  : {profile['case_studies'] or ['None yet']}\n"
                f"KPIs          : {profile['kpis']}"
            )

            ag = Agent(
                role=ac["department_rep"]["role"].format(dept_name=dept_name),
                goal=ac["department_rep"]["goal"].format(dept_name=dept_name),
                backstory=ac["department_rep"]["backstory"].format(
                    dept_name=dept_name,
                    company_name=COMPANY.name,
                    dept_profile=profile_str,
                ),
                llm=get_llm(fast=True),  # cheap model for dept reps
                verbose=True,
            )

            t = Task(
                description=tc["dept_bid_task"]["description"].format(
                    dept_name=dept_name,
                    contract_summary=contract_summary,
                ),
                expected_output=tc["dept_bid_task"]["expected_output"],
                agent=ag,
                output_pydantic=DepartmentBid,
                async_execution=True,  # all dept reps bid in parallel
            )

            dept_agents.append(ag)
            dept_bid_tasks.append(t)

        auctioneer = Agent(
            role=ac["auctioneer"]["role"],
            goal=ac["auctioneer"]["goal"],
            backstory=ac["auctioneer"]["backstory"],
            llm=get_llm(),
            verbose=True,
        )
        auction_task = Task(
            description=tc["auction_task"]["description"].format(
                contract_summary=contract_summary,
                total_word_limit=total_word_limit,
            ),
            expected_output=tc["auction_task"]["expected_output"],
            agent=auctioneer,
            context=dept_bid_tasks,  # waits for all async dept reps
            output_pydantic=AuctionResult,
        )

        architect = Agent(
            role=ac["proposal_architect"]["role"],
            goal=ac["proposal_architect"]["goal"],
            backstory=ac["proposal_architect"]["backstory"],
            tools=[ProposalWriterTool()],
            llm=get_llm(),
            verbose=True,
        )
        proposal_task = Task(
            description=tc["proposal_task"]["description"].format(
                contract_summary=contract_summary,
                company_name=COMPANY.name,
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
        )
        return built_crew, proposal_task
