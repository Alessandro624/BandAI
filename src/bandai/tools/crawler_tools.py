from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Type

from crewai.tools import BaseTool  # type: ignore
from pydantic import BaseModel, Field, field_validator

log = logging.getLogger(__name__)


# Input Schemas


class CrawlerInput(BaseModel):
    portal_name: str = Field(..., description="Human-readable name of the portal to crawl.")
    base_url: str = Field(..., description="Entry URL of the portal to crawl.")
    keywords: list[str] = Field(..., description="List of keywords to search for in the portal.")
    max_results: int = Field(10, description="Maximum number of contracts to return.")

    @field_validator("keywords", mode="before")
    @classmethod
    def parse_keywords(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [v]
        return v


class ContractLookupInput(BaseModel):
    contract_id: str = Field(..., description="Unique identifier of the contract to look up.")
    portal_url: str = Field(..., description="Portal URL where the contract was found.")


class DocumentGeneratorInput(BaseModel):
    title: str = Field(..., description="Title of the document to generate.")
    sections: dict[str, str] = Field(..., description="section_title to markdown_content mapping.")
    output_path: str = Field("output/proposal_output.md", description="File path for the generated document.")


class ComplianceInput(BaseModel):
    tender_raw_text: str = Field(..., description="Raw text of the tender document to analyze.")
    company_profile_json: str = Field(..., description="JSON string containing the company profile.")


# Tools


class TenderCrawlerTool(BaseTool):
    """Crawls a procurement portal and returns matching tender notices as JSON."""

    name: str = "TenderCrawlerTool"
    description: str = (
        "Crawls a given procurement portal and returns all matching tender notices "
        "as a JSON array. Input: portal_name, base_url, keywords, "
        "optional max_results (default 10). Output: JSON array of tender notices "
        "with metadata and raw text."
    )
    args_schema: Type[BaseModel] = CrawlerInput

    def _run(self, portal_name: str, base_url: str, keywords: list[str], max_results: int = 10) -> str:
        log.info("TenderCrawlerTool: crawling %s (max_results=%d)", portal_name, max_results)

        # TODO: Implement actual crawling logic with already CrewAI tools like SeleniumTool or HTTPTool, and parse results into structured JSON.
        # This stub returns mock data so the pipeline can be tested end-to-end
        # before the real crawler is implemented.
        mock_response = [
            {
                "portal": portal_name,
                "url": f"{base_url}/tender/{i}",
                "title": f"Mock Tender {i} with keywords {', '.join(keywords)}",
                "contract_id": f"tender-{random.randint(1000, 9999)}{i}",
                "contracting_authority": f"Authority {i}",
                "deadline": f"2024-0{(i % 9) + 1}-31",
                "value_euros": random.randint(10000, 1000000),
                "raw_text": f"This is the raw text of mock tender {i}, containing keywords {', '.join(keywords)}.",
            }
            for i in range(1, max_results + 1)
        ]
        return json.dumps(mock_response, ensure_ascii=False, indent=2)


class ContractDetailTool(BaseTool):
    """Fetches full metadata of a single tender by Contract ID from the ANAC open API."""

    name: str = "ContractDetailTool"
    description: str = (
        "Given a contract ID and a portal URL, fetches the complete tender notice "
        "including annexes and administrative documents. "
        "Input: contract_id, portal_url. Output: JSON with all available metadata "
        "and a completeness score."
    )
    args_schema: Type[BaseModel] = ContractLookupInput

    def _run(self, contract_id: str, portal_url: str) -> str:
        log.info("ContractDetailTool: looking up contract %s from %s", contract_id, portal_url)

        # TODO: Implement actual contract detail lookup
        # (GET https://dati.anticorruzione.it/opendata/dataset/.../contract-id/{contract_id}).
        mock_response = {
            "contract_id": contract_id,
            "source_url": portal_url,
            "completeness_score": round(random.uniform(0.5, 1.0), 2),
            "has_technical_spec": random.choice([True, False]),
            "has_admin_clauses": random.choice([True, False]),
            "has_award_criteria": random.choice([True, False]),
        }
        return json.dumps(mock_response, ensure_ascii=False, indent=2)


class ComplianceCheckerTool(BaseTool):
    """Cross-references company certifications and financials against tender requirements."""

    name: str = "ComplianceCheckerTool"
    description: str = (
        "Given a tender's raw text and the company profile JSON, returns a "
        "structured gap analysis: requirements met, missing, and uncertain. "
        "Input: tender_raw_text, company_profile_json. Output: JSON with lists "
        "of met, missing, and uncertain requirements."
    )
    args_schema: Type[BaseModel] = ComplianceInput

    def _run(self, tender_raw_text: str, company_profile_json: str) -> str:
        log.info("ComplianceCheckerTool: analyzing compliance for tender (%d chars)", len(tender_raw_text))

        # TODO: Implement actual compliance checking logic (NLP extraction).
        analysis = {
            "met": [
                "Requirement A: Met",
                "Requirement B: Met",
                "Experience in past PA: 2 contracts in the last 3 years",
            ],
            "missing": ["Requirement C: Missing", "Certification X: Not held"],
            "uncertain": [
                "Requirement D: Uncertain",
                "Financial Stability: Needs Review",
            ],
        }
        return json.dumps(analysis, ensure_ascii=False, indent=2)


class ProposalWriterTool(BaseTool):
    """Writes a Markdown proposal document from structured sections to disk."""

    name: str = "ProposalWriterTool"
    description: str = (
        "Assembles a full proposal in Markdown from a title and a dict of "
        "section_title to markdown_content. Writes the output to disk at the "
        "specified path. Input: title, sections (dict), output_path. "
        "Output: Confirmation message with the file path."
    )
    args_schema: Type[BaseModel] = DocumentGeneratorInput

    def _run(self, title: str, sections: dict[str, str], output_path: str) -> str:
        log.info("ProposalWriterTool: writing proposal to %s", output_path)

        lines = [f"# {title}\n\n"]
        for section_title, content in sections.items():
            lines.append(f"## {section_title}\n\n{content}\n\n")
        document_content = "\n".join(lines)

        # Ensure parent directories exist
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        try:
            path.write_text(document_content, encoding="utf-8")
            return f"Proposal written to {output_path}"
        except IOError as e:
            log.error("Failed to write proposal to %s: %s", output_path, e)
            return f"Error writing proposal to {output_path}: {e}"
