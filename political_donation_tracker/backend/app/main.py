from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .fec_client import FecClient
from .llm import generate_financial_summary, generate_pac_summary
from .models import CandidateProfile, CandidateSummary, DonorRow, PacProfile, PacSummary
from .photos import lookup_photo_url


fec: FecClient | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global fec
    fec = FecClient()
    try:
        yield
    finally:
        await fec.close()


app = FastAPI(title="Political Donation Tracker", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _client() -> FecClient:
    if fec is None:
        raise HTTPException(503, "FEC client not ready")
    return fec


def _default_cycle(cycles: list[int], cycle: int | None) -> int:
    if cycle:
        return cycle
    if cycles:
        return max(cycles)
    return 2024


def _fec_http_error(exc: httpx.HTTPStatusError, prefix: str) -> HTTPException:
    if getattr(exc, "response", None) is not None and exc.response.status_code == 429:
        return HTTPException(
            429,
            "FEC rate limit hit. Get a free API key at https://api.data.gov/signup/ "
            "and set FEC_API_KEY in backend/.env, then restart the server.",
        )
    return HTTPException(502, f"{prefix}: {exc}")


async def _with_candidate_photo(candidate: CandidateSummary) -> CandidateSummary:
    if candidate.photo_url:
        return candidate
    photo_url = await lookup_photo_url(
        candidate.name,
        state=candidate.state,
        office_full=candidate.office_full,
    )
    return candidate.model_copy(update={"photo_url": photo_url})


async def _with_pac_photo(pac: PacSummary) -> PacSummary:
    if pac.photo_url:
        return pac
    photo_url = await lookup_photo_url(pac.name, office_full=pac.committee_type_full or "PAC")
    return pac.model_copy(update={"photo_url": photo_url})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/candidates/search", response_model=list[CandidateSummary])
async def search_candidates(q: str = Query(..., min_length=2)) -> list[CandidateSummary]:
    try:
        results = await _client().search_candidates(q)
        return list(await asyncio.gather(*[_with_candidate_photo(row) for row in results]))
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC search failed") from err
    except Exception as err:
        raise HTTPException(502, f"FEC search failed: {err}") from err


@app.get("/pacs/search", response_model=list[PacSummary])
async def search_pacs(q: str = Query(..., min_length=2)) -> list[PacSummary]:
    try:
        # Skip photo enrichment on search to stay within FEC rate limits.
        return await _client().search_pacs(q)
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC PAC search failed") from err
    except Exception as err:
        raise HTTPException(502, f"FEC PAC search failed: {err}") from err


@app.get("/pacs/{committee_id}/profile", response_model=PacProfile)
async def pac_profile(
    committee_id: str,
    cycle: int | None = None,
    limit: int = Query(15, ge=1, le=50),
    include_history: bool = False,
) -> PacProfile:
    client = _client()
    try:
        pac = await _with_pac_photo(await client.get_pac(committee_id))
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC PAC lookup failed") from err
    except ValueError as err:
        raise HTTPException(404, str(err)) from err
    except Exception as err:
        raise HTTPException(502, f"FEC PAC lookup failed: {err}") from err

    resolved_cycle = _default_cycle(pac.cycles, cycle)

    try:
        totals = await client.get_committee_totals(committee_id, resolved_cycle)
        party_breakdown, gifts = await client.pac_giving(
            committee_id,
            resolved_cycle,
            recipient_limit=min(max(limit, 10), 12),
            gift_limit=limit,
        )
        party_history = [party_breakdown]
        if include_history:
            older = sorted(
                [c for c in pac.cycles if c < resolved_cycle],
                reverse=True,
            )[:2]
            if older:
                try:
                    party_history.extend(
                        await client.pac_party_history(
                            committee_id,
                            older,
                            recipient_limit=10,
                        )
                    )
                except httpx.HTTPStatusError:
                    pass
            party_history.sort(key=lambda row: row.cycle, reverse=True)
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC PAC data fetch failed") from err
    except Exception as err:
        raise HTTPException(502, f"FEC PAC data fetch failed: {err}") from err

    summary = await generate_pac_summary(
        pac=pac,
        cycle=resolved_cycle,
        totals=totals,
        party=party_breakdown,
        party_history=party_history,
        gifts=gifts,
    )

    return PacProfile(
        pac=pac,
        cycle=resolved_cycle,
        totals=totals,
        party_breakdown=party_breakdown,
        party_history=party_history,
        politician_gifts=gifts,
        llm_summary=summary,
    )


@app.get("/candidates/{candidate_id}/profile", response_model=CandidateProfile)
async def candidate_profile(
    candidate_id: str,
    cycle: int | None = None,
    donor_type: Literal["all", "individual", "pac", "superpac", "organization"] = "individual",
    limit: int = Query(25, ge=1, le=50),
) -> CandidateProfile:
    client = _client()
    try:
        candidate = await _with_candidate_photo(await client.get_candidate(candidate_id))
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC candidate lookup failed") from err
    except ValueError as err:
        raise HTTPException(404, str(err)) from err
    except Exception as err:
        raise HTTPException(502, f"FEC candidate lookup failed: {err}") from err

    resolved_cycle = _default_cycle(candidate.cycles, cycle)
    committee_id = candidate.principal_committee_id

    totals = None
    top_individuals: list[DonorRow] = []
    top_pacs: list[DonorRow] = []
    top_orgs: list[DonorRow] = []
    superpacs: list[DonorRow] = []

    try:
        totals = await client.get_totals(candidate_id, resolved_cycle)

        if committee_id and donor_type in ("all", "individual"):
            top_individuals = await client.top_individual_donors(
                committee_id, resolved_cycle, limit=limit
            )
        if committee_id and donor_type in ("all", "pac"):
            top_pacs = await client.top_pac_donors(committee_id, resolved_cycle, limit=limit)
        if committee_id:
            top_orgs = await client.top_organizations(committee_id, resolved_cycle, limit=limit)
        if donor_type in ("all", "superpac"):
            superpacs = await client.superpac_activity(candidate_id, resolved_cycle, limit=limit)
    except httpx.HTTPStatusError as err:
        raise _fec_http_error(err, "FEC data fetch failed") from err
    except Exception as err:
        raise HTTPException(502, f"FEC data fetch failed: {err}") from err

    if donor_type == "individual":
        donors = top_individuals
    elif donor_type == "pac":
        donors = top_pacs
    elif donor_type == "superpac":
        donors = superpacs
    elif donor_type == "organization":
        donors = top_orgs
    else:
        donors = sorted(
            [*top_individuals, *top_pacs],
            key=lambda row: row.total,
            reverse=True,
        )[:limit]

    summary = await generate_financial_summary(
        candidate=candidate,
        cycle=resolved_cycle,
        totals=totals,
        top_donors=donors,
        top_organizations=top_orgs,
        superpac_activity=superpacs,
    )

    return CandidateProfile(
        candidate=candidate,
        cycle=resolved_cycle,
        totals=totals,
        top_donors=donors,
        top_organizations=top_orgs,
        superpac_activity=superpacs,
        llm_summary=summary,
    )
