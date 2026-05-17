from __future__ import annotations

import logging
from pathlib import Path

import yaml
from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.project import CrewBase, crew  # type: ignore
from crewai.agents.agent_builder.base_agent import BaseAgent  # type: ignore
from crewai import TaskOutput  # type: ignore

from bandai.config import get_llm, _MAX_REVIEW_ITERATIONS
from bandai.knowledge_sources import get_all_knowledge_sources
from bandai.models import AdvocateAnalysis, AuditorChallenge, ComplianceVerdict, load_company_profile
from bandai.tools.crawler_tools import ComplianceCheckerTool

log = logging.getLogger(__name__)

_CFG = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((_CFG / filename).read_text(encoding="utf-8"))


# Guardrails


def _validate_verdict(result: TaskOutput) -> tuple[bool, TaskOutput]:
    """Ensure the compliance verdict has a valid bid_decision."""
    try:
        verdict = result.pydantic
    except Exception:
        return (False, "Could not parse output as ComplianceVerdict JSON.")
    if verdict.bid_decision not in ("GO", "NO-GO", "CONDITIONAL-GO"):
        return (
            False,
            f"bid_decision must be GO, NO-GO, or CONDITIONAL-GO; got '{verdict.bid_decision}'.",
        )
    if verdict.compliance_score < 0.0 or verdict.compliance_score > 1.0:
        return (
            False,
            f"compliance_score must be between 0.0 and 1.0; got {verdict.compliance_score}.",
        )
    return (True, result)


def _validate_review_verdict(result: TaskOutput) -> tuple[bool, TaskOutput]:
    """Validate the human review re-evaluation verdict."""
    return _validate_verdict(result)


# Crew Class


@CrewBase
class ComplianceCrew:
    """
    Compliance Crew - runs a structured advocate/auditor debate to produce
    a bid verdict.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    agents_config = "config/agents_compliance.yaml"
    tasks_config = "config/tasks_compliance.yaml"

    def build(self, contract_summary: str) -> tuple[Crew, Task]:
        """Build and return (crew, verdict_task) for a specific contract."""
        ac = _load_yaml("agents_compliance.yaml")
        tc = _load_yaml("tasks_compliance.yaml")

        company = load_company_profile()

        profile_vars = dict(
            contract_summary=contract_summary,
            company_name=company.name,
            certifications=", ".join(company.certifications),
            turnover=str(company.turnover_last_3y_eur),
            past_contracts=str([c.model_dump() for c in company.past_public_contracts]),
        )

        # Advocate (optimistic)
        advocate = Agent(
            role=ac["advocate"]["role"],
            goal=ac["advocate"]["goal"],
            backstory=ac["advocate"]["backstory"],
            tools=[ComplianceCheckerTool()],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
        )
        advocate_task = Task(
            description=tc["advocate_task"]["description"].format(**profile_vars),
            expected_output=tc["advocate_task"]["expected_output"],
            agent=advocate,
            output_pydantic=AdvocateAnalysis,
        )

        # Auditor (skeptical) - reads Advocate output via context
        auditor = Agent(
            role=ac["auditor"]["role"],
            goal=ac["auditor"]["goal"],
            backstory=ac["auditor"]["backstory"],
            tools=[ComplianceCheckerTool()],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
        )
        auditor_task = Task(
            description=tc["auditor_task"]["description"].format(**profile_vars),
            expected_output=tc["auditor_task"]["expected_output"],
            agent=auditor,
            context=[advocate_task],
            output_pydantic=AuditorChallenge,
        )

        # Compliance Officer - synthesises debate into verdict
        compliance_officer = Agent(
            role=ac["compliance_officer"]["role"],
            goal=ac["compliance_officer"]["goal"],
            backstory=ac["compliance_officer"]["backstory"],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
            reasoning=True,  # reflect-and-plan for complex legal synthesis
        )
        verdict_task = Task(
            description=tc["verdict_task"]["description"].format(**profile_vars),
            expected_output=tc["verdict_task"]["expected_output"],
            agent=compliance_officer,
            context=[advocate_task, auditor_task],
            output_pydantic=ComplianceVerdict,
            guardrail=_validate_verdict,
            guardrail_max_retries=3,
        )

        built_crew = Crew(
            agents=[advocate, auditor, compliance_officer],
            tasks=[advocate_task, auditor_task, verdict_task],
            process=Process.sequential,
            verbose=True,
            memory=True,
            knowledge_sources=get_all_knowledge_sources(),
        )
        return built_crew, verdict_task

    def build_review(
        self,
        contract_summary: str,
        original_verdict: ComplianceVerdict,
        human_note: str,
        iteration: int = 1,
    ) -> tuple[Crew, Task]:
        """Build a review crew for CONDITIONAL-GO re-evaluation."""
        ac = _load_yaml("agents_compliance.yaml")
        tc = _load_yaml("tasks_compliance.yaml")

        reviewer = Agent(
            role=ac["human_input_review_agent"]["role"],
            goal=ac["human_input_review_agent"]["goal"],
            backstory=ac["human_input_review_agent"]["backstory"],
            llm=get_llm(),
            verbose=True,
            max_retry_limit=2,
            respect_context_window=True,
            inject_date=True,  # deadline-aware review
        )

        review_task = Task(
            description=tc["human_review_task"]["description"].format(
                original_verdict_json=original_verdict.model_dump_json(indent=2),
                human_note=human_note,
                iteration=iteration,
                max_iterations=_MAX_REVIEW_ITERATIONS,
            ),
            expected_output=tc["human_review_task"]["expected_output"],
            agent=reviewer,
            output_pydantic=ComplianceVerdict,
            guardrail=_validate_review_verdict,
            guardrail_max_retries=3,
        )

        review_crew = Crew(
            agents=[reviewer],
            tasks=[review_task],
            process=Process.sequential,
            verbose=True,
            knowledge_sources=get_all_knowledge_sources(),
        )
        return review_crew, review_task

    @crew
    def crew(self) -> Crew:
        """Creates the Compliance Crew."""
        return self.build(contract_summary="")[0]
