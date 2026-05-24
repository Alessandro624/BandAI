from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Literal
import datetime as dt

### -----------------------------------------------------------------------------------
###
###     Discovery Agents - Tender Overview Models
###
### -----------------------------------------------------------------------------------

AccessMode = Literal['api', 'html']
Status = Literal['success', 'error', 'partial']

class TenderOverview(BaseModel):
    """
    Output Template for the Discovery Agent.
    It contains an Information overview of the different available Tenders on a Portal.
    """
    title: Optional[str] = Field(
        default = None, 
        description = "Tender title (if available) from Terders' lists"
    )
    url: HttpUrl = Field(description = "Direct URL page/endpoint for reaching tenders Information")
    
    portal: str = Field(description = "Orginal Portal's Name (i.e. ANAC, TED, MePA)")

    access_mode: AccessMode = Field(
        default = 'html',
        description = "Extration Access Mode"
    )

    metadata: Optional[dict] = Field(
        default = None,
        description = "Avaible Data during the Discovery Process (i.e. CIG, deadline)"
    )

    discovery_datetime: dt.datetime = Field(
        default_factory = dt.datetime.now,
        description = "Timestamp of first discovery of the tender"
    )


class DiscoveryResult(BaseModel):
    """
    It contains a list of discovered tenders on a portal by a Discovery Agent.
    """

    tenders: list[TenderOverview]
    portal: str
    status: Status = 'success'
    error: Optional[str] = None

    @property
    def tenders_count(self):
        return len(self.tenders)



### -----------------------------------------------------------------------------------
###
###     Extractor Agents - Tender Complete Information Models 
###
### -----------------------------------------------------------------------------------

class ContractingAuthority(BaseModel):
    """
    Contracting Authority Information of a Tender
    """

    name: str
    tax_code: Optional[str] = None
    pec: Optional[str] = None
    rup: Optional[str] = None
    

class TenderInfo(BaseModel):
    """
    Output Template for the Extractor Agent.
    It contains all the Information Available of a Tender in a structured way.
    """

    ## Identifiers

    cig: Optional[str] = Field(default = None, description = "Identification Bid Code")
    cup: Optional[str] = Field(default = None, description = "Unified Project Code")
    title: str
    url: HttpUrl

    ## Classification
    cpv: Optional[list[str]] = Field(
        default = None,
        description = "CPV Codes list (i.e. ['72000000', '48000000'])"
    )
    contract_type: Optional[str] = Field(
        default = None,
        description = "Services / Supplies / Construction Work"
    )

    ## Contracting Authority
    contracting_authority: Optional[ContractingAuthority] = None

    ## Economical Value
    base_amount: Optional[float] = Field(default = None, description = "Base auction amount  in Euros")
    max_amount: Optional[float] = Field(default = None, description = "Maximum value, including renewals")
    # award_criterion: Optional[str] = Field(
    #     default = None,
    #     description = "OEPV (quality + price) or OPB (price only)"
    # )

    ## Date Information
    publication_date: Optional[dt.date] = None
    deadline: Optional[dt.datetime] = Field(
        default = None,
        description="Bid submission deadline"
    )
    contract_duration_months: Optional[int] = None

    ## Requirements (as Text)
    # financial_requirements: Optional[str] = None
    # techincal_requirements: Optional[str] = None

    ## Documentation
    url_docs: Optional[list[HttpUrl]] = Field(
        default = None,
        description = "Links to tender documents, specifications, and PDF attachments"
    )

    ## Extraction Meta Data
    portal: str
    extraction_date: dt.datetime = Field(default_factory = dt.datetime.now)
    status: Status = Field(
        default = 'success',
        description = "'success', 'partial' (for missing fields), 'error'"
    )
    error: Optional[str] = None


if __name__ == "__main__":

    tenders_list = []

    for i in range(2):
        tender_overview = TenderOverview(
            title = f"Title {i}",
            url=f"https://dati.anticorruzione.it/api/gara/{i + 234}",
            portal = "ANAC",
            access_mode = 'api' if (i % 2 == 0) else "html",
            metadata = {} if (i % 2 == 0) else dict(cig='ABC1234567')
        )

        tenders_list.append(tender_overview)

discovery_result = DiscoveryResult(
    tenders = tenders_list,
    portal = "ANAC",
    tenders_count = len(tenders_list),
    status = 'success',
)


print(discovery_result.model_dump_json(indent=2))
