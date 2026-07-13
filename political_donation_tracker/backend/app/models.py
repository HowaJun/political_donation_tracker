from typing import Literal

from pydantic import BaseModel, Field


DonorType = Literal["individual", "pac", "superpac", "organization", "all"]


class CandidateSummary(BaseModel):
    candidate_id: str
    name: str
    office: str | None = None
    office_full: str | None = None
    party: str | None = None
    party_full: str | None = None
    state: str | None = None
    district: str | None = None
    cycles: list[int] = Field(default_factory=list)
    principal_committee_id: str | None = None
    principal_committee_name: str | None = None
    photo_url: str | None = None


class PacSummary(BaseModel):
    committee_id: str
    name: str
    committee_type: str | None = None
    committee_type_full: str | None = None
    designation: str | None = None
    designation_full: str | None = None
    party: str | None = None
    party_full: str | None = None
    state: str | None = None
    cycles: list[int] = Field(default_factory=list)
    treasurer_name: str | None = None
    photo_url: str | None = None


class FinancialTotals(BaseModel):
    cycle: int
    receipts: float = 0
    disbursements: float = 0
    contributions: float = 0
    individual_contributions: float = 0
    other_political_committee_contributions: float = 0
    political_party_committee_contributions: float = 0
    cash_on_hand: float = 0
    debts_owed: float = 0
    coverage_start_date: str | None = None
    coverage_end_date: str | None = None
    fed_candidate_committee_contributions: float = 0


class DonorRow(BaseModel):
    name: str
    total: float
    count: int = 1
    donor_type: DonorType
    detail: str | None = None


class PartyBreakdown(BaseModel):
    cycle: int
    democratic: float = 0
    republican: float = 0
    other: float = 0
    unknown: float = 0


class PoliticianGift(BaseModel):
    name: str
    total: float
    count: int = 0
    party: str | None = None
    party_full: str | None = None
    candidate_id: str | None = None
    committee_id: str | None = None
    office: str | None = None


class CandidateProfile(BaseModel):
    candidate: CandidateSummary
    cycle: int
    totals: FinancialTotals | None = None
    top_donors: list[DonorRow] = Field(default_factory=list)
    top_organizations: list[DonorRow] = Field(default_factory=list)
    superpac_activity: list[DonorRow] = Field(default_factory=list)
    llm_summary: str = ""


class PacProfile(BaseModel):
    pac: PacSummary
    cycle: int
    totals: FinancialTotals | None = None
    party_breakdown: PartyBreakdown | None = None
    party_history: list[PartyBreakdown] = Field(default_factory=list)
    politician_gifts: list[PoliticianGift] = Field(default_factory=list)
    llm_summary: str = ""
