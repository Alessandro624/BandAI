from __future__ import annotations

import yaml
from pathlib import Path
from crewai import Agent, Crew, Process, Task  # type: ignore
from crewai.project import CrewBase  # type: ignore

from bandai.config import COMPANY, get_llm, _MAX_REVIEW_ITERATIONS
from bandai.models import AdvocateAnalysis, AuditorChallenge, ComplianceVerdict
from bandai.tools.crawler_tools import ComplianceCheckerTool

_CFG = Path(__file__).parent.parent / "config"


def _load_yaml(filename: str) -> dict:
    return yaml.safe_load((_CFG / filename).read_text(encoding="utf-8"))


@CrewBase
class ComplianceCrew:
    """Compliance Crew - runs a structured debate to produce a bid verdict."""

    def build(self, contract_summary: str) -> tuple[Crew, Task]:
        """
        Build and return (crew, verdict_task) for a specific contract.
        verdict_task.output.pydantic is a ComplianceVerdict.
        """
        ac = _load_yaml("agents_compliance.yaml")
        tc = _load_yaml("tasks_compliance.yaml")

        # Shared interpolation values
        profile_vars = dict(
            contract_summary=contract_summary,
            company_name=COMPANY.name,
            certifications=", ".join(COMPANY.certifications),
            turnover=str(COMPANY.turnover_last_3y_eur),
            past_contracts=str(COMPANY.past_public_contracts),
        )

        # Advocate
        advocate = Agent(
            role=ac["advocate"]["role"],
            goal=ac["advocate"]["goal"],
            backstory=ac["advocate"]["backstory"],
            tools=[ComplianceCheckerTool()],
            llm=get_llm(),
            verbose=True,
        )
        advocate_task = Task(
            description=tc["advocate_task"]["description"].format(**profile_vars),
            expected_output=tc["advocate_task"]["expected_output"],
            agent=advocate,
            output_pydantic=AdvocateAnalysis,
        )

        # Auditor (reads Advocate output via context)
        auditor = Agent(
            role=ac["auditor"]["role"],
            goal=ac["auditor"]["goal"],
            backstory=ac["auditor"]["backstory"],
            tools=[ComplianceCheckerTool()],
            llm=get_llm(),
            verbose=True,
        )
        auditor_task = Task(
            description=tc["auditor_task"]["description"].format(**profile_vars),
            expected_output=tc["auditor_task"]["expected_output"],
            agent=auditor,
            context=[advocate_task],  # debate: Auditor reads Advocate
            output_pydantic=AuditorChallenge,
        )

        # Compliance Officer (reads both, issues verdict)
        compliance_officer = Agent(
            role=ac["compliance_officer"]["role"],
            goal=ac["compliance_officer"]["goal"],
            backstory=ac["compliance_officer"]["backstory"],
            llm=get_llm(),
            verbose=True,
        )
        verdict_task = Task(
            description=tc["verdict_task"]["description"].format(**profile_vars),
            expected_output=tc["verdict_task"]["expected_output"],
            agent=compliance_officer,
            context=[advocate_task, auditor_task],  # synthesises debate
            output_pydantic=ComplianceVerdict,
        )

        built_crew = Crew(
            agents=[advocate, auditor, compliance_officer],
            tasks=[advocate_task, auditor_task, verdict_task],
            process=Process.sequential,
            verbose=True,
        )
        return built_crew, verdict_task

    def build_review(
        self,
        contract_summary: str,
        original_verdict: ComplianceVerdict,
        human_note: str,
        iteration: int = 1,
    ) -> tuple[Crew, Task]:
        ac = _load_yaml("agents_compliance.yaml")
        tc = _load_yaml("tasks_compliance.yaml")

        reviewer = Agent(
            role=ac["human_input_review_agent"]["role"],
            goal=ac["human_input_review_agent"]["goal"],
            backstory=ac["human_input_review_agent"]["backstory"],
            llm=get_llm(),
            verbose=True,
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
        )

        build_crew = Crew(
            agents=[reviewer],
            tasks=[review_task],
            process=Process.sequential,
            verbose=True,
        )
        return build_crew, review_task
