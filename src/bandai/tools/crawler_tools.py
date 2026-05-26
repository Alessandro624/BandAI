from __future__ import annotations

import json
import logging
import random
import asyncio

from pathlib import Path
from typing import Type, Literal, Optional

from crewai.tools import BaseTool  # type: ignore
from pydantic import BaseModel, HttpUrl, Field, field_validator

from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout

from bandai.config import BANDI_PORTALS
from bandai.config.portals import (
    PortalConfig,
    SelectorIdentifier, ActionDescription, 
    DiscoveryProcess, ExtractionProcess
)
from bandai.utils import html_to_markdown

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
                "value_eur": float(random.randint(10000, 1000000)),
                "cpv_codes": [],
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



### -----------------------------------------------------------------------------------
###
###     Defining Tools for Discovery and Construction of Tenders Overview
###
### -----------------------------------------------------------------------------------

PROCESS_CONFIG: dict[str, PortalConfig] = { 
    portal.name: portal for portal in BANDI_PORTALS
}

DISCOVERABLE_PORTALS: dict[str, PortalConfig] = {
    portal.name: portal for portal in BANDI_PORTALS if portal.is_ready_for_discovery()
}

## Input Schema
class TendersOverviewExtractorInput(BaseModel):
    """
    Input Schema for the Tenders' Overview Extraction Tool.
    """
    portal_name: str = Field(description = "Available Portal Name to reach.")
    tenders_count: int = Field(
        default = 10,
        description = "Number of Tenders to get from the Portal"
    )


## Main Tool Class
class TendersOverviewExtractorTool(BaseTool):
    """
    Navigates a tender listing portal, given as input, across multiple pages and 4
    returns all tenders found in Markdown format.
    In this way, the content is LLM-ready to be parsed into custom data structures (TenderOverview).
    Pagination and portal-specific actions are handled based on the portal configuration file.
    """

    name: str = "Tenders' Overview Extractor"
    description: str = (
        "This Tool can nagigate a portal searching for different tenders, presented in a list format."
        "It can handle pagination automatically."
        "All the content will be turned into Markdown format - parsable to extract TenderOverview objects."
    )
    args_schema: type[BaseModel] = TendersOverviewExtractorInput

    ## Internal Config
    max_chars: int = 12_000
    timeout_ms: int = 30_000
    headless_mode: bool = True #### DEBUG


    def _run(self, portal_name: str, tenders_count: int) -> str:
        """
        Synchronous entry point for CrewAI Agent.
        """
        return asyncio.run(self._extract(portal_name, tenders_count))

    async def _extract(self, portal_name: str, tenders_count: int) -> str:
        """
        Loads asynchronously a Web Page containing a list-like content and returns its content in Markdown Format.

        Performed Steps:
            1. Read the Portal Configuration to perform the process.
            2. Opens Playwright in headless mode.
            3. If provided, applies portal-specific actions on the first page (Main table interacion).
            4. Extract the list wrapper HTML content
            5. Converts the content into Markdown through a utility function.
            6. Loops over pages if needed.
            7. Returns the aggregated Markdown content for the Agent to parse
        """

        ### Portal Name configuration:
        if portal_name not in DISCOVERABLE_PORTALS.keys():
            return self._error(
                portal_name = portal_name, 
                error_message = (
                    "No Configuration found for the current portal. "
                    f"Available: { list(DISCOVERABLE_PORTALS.keys()) }"
                )
            )
        
        portal_cfg: DiscoveryProcess = DISCOVERABLE_PORTALS[portal_name].discovery
        
        search_url: str = str(portal_cfg.base_search_url)

        elements_per_page: int = portal_cfg.elements_per_page
        max_pages: int = (tenders_count // elements_per_page) + 1
        max_lines_on_last_page: int = (tenders_count % elements_per_page) + 1

        if max_lines_on_last_page == 1:
            max_pages -= 1
            max_lines_on_last_page = None

        pages_markdown: list[str] = []

        ## Main Instruction Process - Playwright Loop
        browser = None
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless = self.headless_mode)
                context = await browser.new_context(
                        user_agent = (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        viewport = { 'width': 1920, 'height': 1080 }
                )
                page = await context.new_page()

                ## Prevents unuseful resources from loading to speed up the loading process
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}",
                    lambda route: route.abort()
                )

                try:
                    ## Main Page
                    await page.goto(
                        search_url,
                        wait_until = "networkidle", ## Waits for the Network traffic to become stable
                        timeout = self.timeout_ms
                    )
                    
                    for page_num in range(max_pages):
                        log.info(f"[TendersOverviewExtraction] [{portal_name}] Page {page_num}/{max_pages}")

                        ## Useful for Filtering or Tag Selection
                        if page_num == 0:
                            await self._do_apply_action_on_first_page(
                                page = page, portal_cfg = portal_cfg
                            )
                        
                        ## List Wrapper - Current Content
                        html = await self._do_get_list_html_content(
                            page = page, portal_cfg = portal_cfg
                        )
                        if not html:
                            log.warning(f"[TendersOverviewExtraction] Empty content on page {page_num}, stopping")
                            break

                        ## Markdown Conversion
                        markdown = html_to_markdown(
                            html,
                            mode = 'discovery',
                            max_lines = max_lines_on_last_page if page_num == max_pages - 1 else None
                        )

                        if markdown.strip():
                            pages_markdown.append(f"<!-- Page {page_num} -->\n{markdown}")
                            log.info(f"[TendersOverviewExtraction] Page {page_num} converted successfully. ({len(markdown)} chars).")
                            
                        
                        ## Go to nex Page
                        has_next = await self._do_go_to_next_page(
                            page = page, portal_cfg = portal_cfg
                        )

                        if not has_next:
                            log.info(f"[TendersOverviewExtraction] No next page after page {page_num}, stopping")
                            break

                except PlaywrightTimeout:
                    log.warning(f"[TendersOverviewExtraction] Timeout on {portal_name}, Partial Recovery of the page.")

                    ## We can try and get all the Content that was already loaded in the page.
                    html = await page.content()
                    if not html:
                        return self._error(portal_name, "Timeout exceeded, empty page.")
                    
                    
                    ## Markdown Extraction
                    markdown = html_to_markdown(html, mode = 'discovery', max_chars = self.max_chars)

                    if not markdown.strip():
                        return self._error(portal_name, "Page loaded successfully, no content found after stripping [Markdown production].")

                    log.info(f"[TendersOverviewExtraction] Extracted {len(markdown)} chars from {portal_name}")
                    
                    return markdown

            except Exception as e:
                log.error(f"[TendersOverviewExtraction] Unexpected Error on {portal_name}: {e}")
                return self._error(portal_name, str(e))

            finally:
                if browser:
                    await browser.close()

        if not pages_markdown:
            return self._error(portal_name, "No content collected across all pages")

        header = (
            f"# Tender listings from {portal_name}\n"
            f"Pages navigated: {len(pages_markdown)}\n\n"
        )
        return header + "\n\n---\n\n".join(pages_markdown)


    ## Support Methods
    def _build_locator(self, selector: SelectorIdentifier) -> str:
        """
        Builds a Playwright locator string from a selector config.
        """
        match selector.type:
            case "css":
                return selector.text
            # case "aria-label":
            #     return f"[aria-label='{cfg['selector_text']}']"

            case _: ## In general [type='content']
                return f"[{selector.type}='{selector.text}']"

    async def _do_apply_action_on_first_page(self, page: Page, portal_cfg: DiscoveryProcess) -> None:
        """
        Applies actions/filter on the main table for the first page.
        Useful for sorting based on Values using dynamic lists, etc.
        """
        ## Apply actions like sorting based on Values using dynamic lists etc.
        for action in (portal_cfg.actions_to_perform or []):
            
            locator_str: str = self._build_locator(action.selector)
            log.info(f"[TendersOverviewExtraction] Applying action \"{action.action_type}\" on element: {locator_str}")
                       
            match action.action_type:
                case "click":
                    await page.locator(locator_str).click()

                    wait = action.wait_after_action or "networkidle"
                    if isinstance(wait, int):
                        await page.wait_for_timeout(wait)
                    else:
                        await page.wait_for_load_state(wait)

    async def _do_get_list_html_content(self, page: Page, portal_cfg: DiscoveryProcess) -> Optional[str]:
        """
        Extracts HTML from the configured list wrapper element.
        """
        wrapper_cfg = portal_cfg.list_wrapper_selector

        # No wrapper configured — fallback to full page
        if not wrapper_cfg:
            return await page.content()

        locator_str = self._build_locator(wrapper_cfg)
        try:
            await page.wait_for_selector(
                locator_str,
                state = 'visible',
                timeout = 10_000
            )

            return await page.locator(locator_str).first.inner_html()
        
        except Exception as e:
            log.warning(f"[TendersOverviewExtraction] Timeout waiting for '{locator_str}': {e}. Falling back to full page.")
            return await page.content()   

    async def _do_go_to_next_page(self, page: Page, portal_cfg: DiscoveryProcess) -> bool:
        """
        Clicks the next page button if available and not disabled.
        Returns True if navigation occurred, False otherwise.
        """
        next_cfg = portal_cfg.next_page_selector
        if not next_cfg:
            return False

        locator_str = self._build_locator(next_cfg)
        next_btn = page.locator(locator_str).first

        if await next_btn.count() == 0:
            return False

        is_disabled = await next_btn.get_attribute("disabled")
        if is_disabled is not None:
            return False

        await next_btn.click()

        ## Waiting for JS to render properly
        await page.wait_for_load_state("networkidle")

        return True               


    def _error(self, portal_name: str, error_message: str) -> str:
        """
        Returns an error message that an Agent can parse.
        """
        return f"[ERROR on TendersOverviewExtraction] Portal: {portal_name} | Reason: {error_message}"
    

### -----------------------------------------------------------------------------------
###
###     Defining Tools for Information Extraction of a Tender
###
### -----------------------------------------------------------------------------------

class SinglePageLoaderInput(BaseModel):
    """
    Input Schema for PageLoaderTool.
    """
    portal_name: str = Field(description = "Name of portal to Portal to reach")
    url: HttpUrl | str = Field(description = "URL of the Tender's Detail Page to Load")

## Main Tool Class
class SinglePageLoaderTool(BaseTool):
    """
    Loads the Content of a Single Web Page and returns the content in a clean Markdown format.
    It can handle both static and dynamic, JS-rendered pages.
    """

    name: str = "Single Page Loader"
    description: str = (
        "It can load a Web Page containg a specific Tender's Details."
        "All the content will be turned into Markdown format - parsable to extract TenderInfo objects."
    )

    args_schema: type[BaseModel] = SinglePageLoaderInput

    ## Internal Config
    max_chars: int = 12_000
    timeout_ms: int = 30_000
    headless_mode: bool = True #### DEBUG

    def _run(self, portal_name: str, url: HttpUrl | str) -> str:
        """
        Synchronous Entry point for CrewAI Agent.
        """
        return asyncio.run(self._load_page(portal_name, str(url)))
    
    async def _load_page(self, portal_name: str, url: str) -> str:
        """
        Loads asynchronously a Web Page and returns its content in Markdown Format.

        Performed Steps:
            1. Opens Playwright in headless mode,
            2. Reaches the page by using the provided url.
            3. Waits for the complete load of the page, if necessary.
            4. Converts the selected HTML Content into Markdown through a utility function.
        """

        ### Portal Name configuration
        portal_cfg: Optional[ExtractionProcess] = None
        if portal_name in PROCESS_CONFIG.keys():
            portal_cfg = PROCESS_CONFIG[portal_name].extraction

        if portal_cfg and not url.startswith('http'):
            url = str(portal_cfg.base_resource_url).rstrip('/') + url

        log.info(f"[SinglePageLoader] Loading: {url} [{portal_name}]")

        ## Main Instruction Process - Playwright Loop
        browser = None
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless = self.headless_mode)
                context = await browser.new_context(
                        user_agent = (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                        viewport = { 'width': 1920, 'height': 1080 }
                )
                page = await context.new_page()

                ## Prevents unuseful resources from loading to speed up the loading process
                await page.route(
                    "**/*.{png,jpg,jpeg,gif,svg,woff,woff2,ttf}",
                    lambda route: route.abort()
                )

                try:
                    await page.goto(
                        url,
                        wait_until = "networkidle",
                        timeout = self.timeout_ms
                    )

                except PlaywrightTimeout:
                    log.warning(f"[SinglePageLoader] Timeout on {url}, attempting partial recovery")

                if portal_cfg:
                    ## Get Main Content on specific portal
                    html = await self._do_get_main_html_content(
                        page = page, portal_cfg = portal_cfg
                    )
                else:
                    ## Generic Fallback
                    html = await page.content()

                if not html:
                    return self._error(url, "Page loaded but returned empty content")


                ## Markdown Conversion
                markdown = html_to_markdown(
                    html,
                    mode = 'extraction',
                    max_chars = self.max_chars
                )

                if not markdown.strip():
                    return self._error(url, "No content found after cleaning")

                log.info(f"[SinglePageLoader] Extracted {len(markdown)} chars from {url}")
                
                return markdown

            except Exception as e:
                log.error(f"[SinglePageLoader] Error on {url}: {e}")
                return self._error(url, str(e))

            finally:
                if browser:
                    await browser.close()

            

    ## Support Methods
    def _build_locator(self, selector: SelectorIdentifier) -> str:
        """
        Builds a Playwright locator string from a selector config.
        """
        match selector.type:
            case "css":
                return selector.text
            case _: ## In general [type='content']
                return f"[{selector.type}='{selector.text}']"

    async def _do_get_main_html_content(self, page: Page, portal_cfg: ExtractionProcess) -> Optional[str]:
        """
        Extracts HTML from the configured list wrapper element.
        """
        wrapper_cfg = portal_cfg.main_content_selector

        # No wrapper configured — fallback to full page
        if not wrapper_cfg:
            return await page.content()
        
        locator_str = self._build_locator(wrapper_cfg)
        try:
            return await page.locator(locator_str).first.inner_html(timeout = 10_000)
        
        except Exception as e:
            log.warning(f"[SinglePageLoader] Element '{locator_str}' not found: {e}, falling back to full page")
            return await page.content()   


    def _error(self, url: str, reason: str) -> str:
        return f"[ERROR SinglePageLoader] URL: {url} | Reason: {reason}"
    
