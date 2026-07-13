from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import httpx

from .config import settings
from .models import (
    CandidateSummary,
    DonorRow,
    FinancialTotals,
    PacSummary,
    PartyBreakdown,
    PoliticianGift,
)


class FecClient:
    def __init__(self) -> None:
        self._cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._client = httpx.AsyncClient(
            base_url=settings.fec_base_url,
            timeout=30.0,
            params={"api_key": settings.fec_api_key},
            verify=settings.fec_ssl_verify,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, path: str, **params: Any) -> dict[str, Any]:
        clean = {k: v for k, v in params.items() if v is not None}
        key = (path, tuple(sorted((k, str(v)) for k, v in clean.items())))
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        response = await self._client.get(path, params=clean)
        response.raise_for_status()
        data = response.json()
        self._cache[key] = data
        return data

    async def search_candidates(self, query: str, per_page: int = 10) -> list[CandidateSummary]:
        data = await self._get(
            "/candidates/search/",
            q=query,
            per_page=per_page,
            sort="name",
        )
        return [self._map_candidate(row) for row in data.get("results", [])]

    async def get_candidate(self, candidate_id: str) -> CandidateSummary:
        data = await self._get(f"/candidate/{candidate_id}/")
        results = data.get("results") or []
        if not results:
            raise ValueError(f"Candidate not found: {candidate_id}")
        return self._map_candidate(results[0])

    async def get_totals(self, candidate_id: str, cycle: int) -> FinancialTotals | None:
        data = await self._get(
            f"/candidate/{candidate_id}/totals/",
            cycle=cycle,
            election_full=False,
        )
        rows = data.get("results") or []
        if not rows:
            return None
        row = rows[0]
        return FinancialTotals(
            cycle=cycle,
            receipts=float(row.get("receipts") or 0),
            disbursements=float(row.get("disbursements") or 0),
            contributions=float(row.get("contributions") or 0),
            individual_contributions=float(row.get("individual_contributions") or 0),
            other_political_committee_contributions=float(
                row.get("other_political_committee_contributions") or 0
            ),
            political_party_committee_contributions=float(
                row.get("political_party_committee_contributions") or 0
            ),
            cash_on_hand=float(row.get("last_cash_on_hand_end_period") or 0),
            debts_owed=float(row.get("last_debts_owed_by_committee") or 0),
            coverage_start_date=_date(row.get("coverage_start_date")),
            coverage_end_date=_date(row.get("coverage_end_date")),
            fed_candidate_committee_contributions=float(
                row.get("fed_candidate_committee_contributions") or 0
            ),
        )

    async def search_pacs(self, query: str, per_page: int = 10) -> list[PacSummary]:
        data = await self._get(
            "/committees/",
            q=query,
            per_page=per_page,
            sort_null_only=False,
        )
        return [self._map_pac(row) for row in data.get("results", [])]

    async def get_pac(self, committee_id: str) -> PacSummary:
        data = await self._get(f"/committee/{committee_id}/")
        results = data.get("results") or []
        if not results:
            raise ValueError(f"PAC/committee not found: {committee_id}")
        return self._map_pac(results[0])

    async def get_committee_totals(self, committee_id: str, cycle: int) -> FinancialTotals | None:
        data = await self._get(f"/committee/{committee_id}/totals/", cycle=cycle)
        rows = data.get("results") or []
        if not rows:
            return None
        row = rows[0]
        return FinancialTotals(
            cycle=cycle,
            receipts=float(row.get("receipts") or 0),
            disbursements=float(row.get("disbursements") or 0),
            contributions=float(row.get("contributions") or 0),
            individual_contributions=float(row.get("individual_contributions") or 0),
            other_political_committee_contributions=float(
                row.get("other_political_committee_contributions") or 0
            ),
            political_party_committee_contributions=float(
                row.get("political_party_committee_contributions") or 0
            ),
            cash_on_hand=float(
                row.get("last_cash_on_hand_end_period")
                or row.get("cash_on_hand_end_period")
                or 0
            ),
            debts_owed=float(row.get("debts_owed_by_committee") or 0),
            coverage_start_date=_date(row.get("coverage_start_date")),
            coverage_end_date=_date(row.get("coverage_end_date")),
            fed_candidate_committee_contributions=float(
                row.get("fed_candidate_committee_contributions") or 0
            ),
        )

    async def pac_giving(
        self,
        committee_id: str,
        cycle: int,
        *,
        recipient_limit: int = 40,
        gift_limit: int = 25,
    ) -> tuple[PartyBreakdown, list[PoliticianGift]]:
        """Aggregate Schedule B gifts to recipient committees by party and politician."""
        data = await self._get(
            "/schedules/schedule_b/by_recipient_id/",
            committee_id=committee_id,
            cycle=cycle,
            sort="-total",
            per_page=min(max(recipient_limit, 10), 100),
        )
        recipients = [
            row
            for row in (data.get("results") or [])
            if str(row.get("recipient_id") or "").startswith("C")
        ]

        details = await asyncio.gather(
            *[self._recipient_committee(str(row["recipient_id"])) for row in recipients],
            return_exceptions=True,
        )

        party = PartyBreakdown(cycle=cycle)
        gifts: list[PoliticianGift] = []

        for row, detail in zip(recipients, details):
            total = float(row.get("total") or 0)
            count = int(row.get("count") or 0)
            if isinstance(detail, Exception) or detail is None:
                party.unknown += total
                continue

            code = (detail.get("party") or "").upper()
            if code in {"DEM", "DFL"}:
                party.democratic += total
            elif code in {"REP", "GOP"}:
                party.republican += total
            elif code:
                party.other += total
            else:
                party.unknown += total

            candidate_ids = detail.get("candidate_ids") or []
            committee_type = (detail.get("committee_type") or "").upper()
            if committee_type in {"H", "S", "P"} or candidate_ids:
                gifts.append(
                    PoliticianGift(
                        name=_titleish(
                            detail.get("name")
                            or row.get("recipient_name")
                            or row.get("recipient_id")
                            or "Unknown"
                        ),
                        total=total,
                        count=count,
                        party=detail.get("party"),
                        party_full=detail.get("party_full"),
                        candidate_id=candidate_ids[0] if candidate_ids else None,
                        committee_id=detail.get("committee_id") or row.get("recipient_id"),
                        office=detail.get("committee_type_full") or detail.get("committee_type"),
                    )
                )

        gifts.sort(key=lambda item: item.total, reverse=True)
        return party, gifts[:gift_limit]

    async def pac_party_history(
        self,
        committee_id: str,
        cycles: list[int],
        *,
        recipient_limit: int = 40,
    ) -> list[PartyBreakdown]:
        history: list[PartyBreakdown] = []
        for cycle in cycles:
            breakdown, _ = await self.pac_giving(
                committee_id,
                cycle,
                recipient_limit=recipient_limit,
                gift_limit=1,
            )
            history.append(breakdown)
        return history

    async def _recipient_committee(self, committee_id: str) -> dict[str, Any] | None:
        data = await self._get(f"/committee/{committee_id}/")
        results = data.get("results") or []
        return results[0] if results else None

    async def top_individual_donors(
        self,
        committee_id: str,
        cycle: int,
        limit: int = 25,
    ) -> list[DonorRow]:
        return await self._aggregate_schedule_a(
            committee_id=committee_id,
            cycle=cycle,
            is_individual=True,
            donor_type="individual",
            limit=limit,
        )

    async def top_pac_donors(
        self,
        committee_id: str,
        cycle: int,
        limit: int = 25,
    ) -> list[DonorRow]:
        """Committee-to-committee receipts reported on Schedule A (PACs, etc.)."""
        return await self._aggregate_schedule_a(
            committee_id=committee_id,
            cycle=cycle,
            is_individual=False,
            donor_type="pac",
            limit=limit,
        )

    async def top_organizations(
        self,
        committee_id: str,
        cycle: int,
        limit: int = 25,
    ) -> list[DonorRow]:
        data = await self._get(
            "/schedules/schedule_a/by_employer/",
            committee_id=committee_id,
            cycle=cycle,
            sort="-total",
            per_page=min(max(limit * 3, 30), 100),
        )
        skip = {
            "",
            "N/A",
            "NA",
            "NONE",
            "NULL",
            "NOT EMPLOYED",
            "UNEMPLOYED",
            "RETIRED",
            "SELF",
            "SELF EMPLOYED",
            "SELF-EMPLOYED",
            "SELF EMPLOYED / SELF-EMPLOYED",
        }
        rows: list[DonorRow] = []
        for row in data.get("results") or []:
            employer = (row.get("employer") or "").strip()
            if not employer or employer.upper() in skip:
                continue
            rows.append(
                DonorRow(
                    name=employer.title() if employer.isupper() else employer,
                    total=float(row.get("total") or 0),
                    count=int(row.get("count") or 0),
                    donor_type="organization",
                    detail="Employer (itemized individuals)",
                )
            )
            if len(rows) >= limit:
                break
        return rows

    async def superpac_activity(
        self,
        candidate_id: str,
        cycle: int,
        limit: int = 25,
    ) -> list[DonorRow]:
        """Independent expenditures supporting/opposing the candidate (often Super PACs)."""
        data = await self._get(
            "/schedules/schedule_e/by_candidate/",
            candidate_id=candidate_id,
            cycle=cycle,
            sort="-total",
            per_page=limit,
        )
        rows: list[DonorRow] = []
        for row in data.get("results") or []:
            indicator = row.get("support_oppose_indicator") or "?"
            label = "support" if indicator == "S" else "oppose" if indicator == "O" else indicator
            rows.append(
                DonorRow(
                    name=row.get("committee_name") or row.get("committee_id") or "Unknown",
                    total=float(row.get("total") or 0),
                    count=int(row.get("count") or 0),
                    donor_type="superpac",
                    detail=f"Independent expenditure ({label})",
                )
            )
        return rows

    async def _aggregate_schedule_a(
        self,
        *,
        committee_id: str,
        cycle: int,
        is_individual: bool,
        donor_type: str,
        limit: int,
        pages: int = 1,
        per_page: int = 50,
    ) -> list[DonorRow]:
        totals: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)

        for page in range(1, pages + 1):
            data = await self._get(
                "/schedules/schedule_a/",
                committee_id=committee_id,
                two_year_transaction_period=cycle,
                is_individual=str(is_individual).lower(),
                per_page=per_page,
                page=page,
                sort="-contribution_receipt_amount",
            )
            results = data.get("results") or []
            if not results:
                break
            for row in results:
                name = (
                    row.get("contributor_name")
                    or row.get("contributor_employer")
                    or "Unknown"
                )
                name = str(name).strip()
                amount = float(row.get("contribution_receipt_amount") or 0)
                totals[name] += amount
                counts[name] += 1

        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
        return [
            DonorRow(
                name=_titleish(name),
                total=total,
                count=counts[name],
                donor_type=donor_type,  # type: ignore[arg-type]
            )
            for name, total in ranked
        ]

    def _map_candidate(self, row: dict[str, Any]) -> CandidateSummary:
        principals = row.get("principal_committees") or []
        principal = principals[0] if principals else {}
        return CandidateSummary(
            candidate_id=row["candidate_id"],
            name=row.get("name") or row["candidate_id"],
            office=row.get("office"),
            office_full=row.get("office_full"),
            party=row.get("party"),
            party_full=row.get("party_full"),
            state=row.get("state"),
            district=row.get("district"),
            cycles=list(row.get("cycles") or []),
            principal_committee_id=principal.get("committee_id"),
            principal_committee_name=principal.get("name"),
        )

    def _map_pac(self, row: dict[str, Any]) -> PacSummary:
        return PacSummary(
            committee_id=row["committee_id"],
            name=row.get("name") or row["committee_id"],
            committee_type=row.get("committee_type"),
            committee_type_full=row.get("committee_type_full"),
            designation=row.get("designation"),
            designation_full=row.get("designation_full"),
            party=row.get("party"),
            party_full=row.get("party_full"),
            state=row.get("state"),
            cycles=list(row.get("cycles") or []),
            treasurer_name=row.get("treasurer_name"),
        )


def _date(value: Any) -> str | None:
    if not value:
        return None
    return str(value)[:10]


def _titleish(value: str) -> str:
    return value.title() if value.isupper() else value
