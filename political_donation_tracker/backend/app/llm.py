from __future__ import annotations

from openai import AsyncOpenAI

from .config import settings
from .models import (
    CandidateSummary,
    DonorRow,
    FinancialTotals,
    PacSummary,
    PartyBreakdown,
    PoliticianGift,
)


SUMMARY_SYSTEM = """You write short, neutral campaign-finance summaries for a Chrome extension.
Rules:
- Exactly 2–3 sentences.
- Use only the provided numbers; do not invent donors or amounts.
- Plain language, no jargon dump. Mention cycle, total raised, mix of individual vs PAC money if present.
- If Super PAC independent expenditures exist, note them briefly as outside direct contributions.
- No advice, no speculation about influence or corruption.
- Lead with the politician's name."""


def format_money(amount: float) -> str:
    if abs(amount) >= 1_000_000:
        return f"${amount / 1_000_000:.1f}M"
    if abs(amount) >= 1_000:
        return f"${amount / 1_000:.0f}K"
    return f"${amount:,.0f}"


def rule_based_summary(
    candidate: CandidateSummary,
    cycle: int,
    totals: FinancialTotals | None,
    top_donors: list[DonorRow],
    superpac_activity: list[DonorRow],
) -> str:
    name = _display_name(candidate.name)
    if not totals:
        return (
            f"{name} has limited FEC totals available for the {cycle} cycle. "
            "Try another election cycle or check back after more reports are filed."
        )

    parts = [
        f"{name} raised {format_money(totals.contributions)} in contributions "
        f"during the {cycle} cycle, with {format_money(totals.individual_contributions)} "
        f"from individuals and {format_money(totals.other_political_committee_contributions)} "
        f"from other political committees."
    ]
    parts.append(
        f"The campaign reported {format_money(totals.cash_on_hand)} cash on hand "
        f"and {format_money(totals.disbursements)} in disbursements."
    )
    if top_donors:
        lead = top_donors[0]
        parts.append(
            f"Among itemized donors sampled, the largest was {lead.name} "
            f"at {format_money(lead.total)}."
        )
    elif superpac_activity:
        lead = superpac_activity[0]
        parts.append(
            f"Independent spending linked to the race includes {lead.name} "
            f"at {format_money(lead.total)}."
        )
    return " ".join(parts[:3])


async def generate_financial_summary(
    candidate: CandidateSummary,
    cycle: int,
    totals: FinancialTotals | None,
    top_donors: list[DonorRow],
    top_organizations: list[DonorRow],
    superpac_activity: list[DonorRow],
) -> str:
    fallback = rule_based_summary(candidate, cycle, totals, top_donors, superpac_activity)
    if not settings.openai_api_key:
        return fallback

    payload = {
        "candidate": candidate.model_dump(),
        "cycle": cycle,
        "totals": totals.model_dump() if totals else None,
        "top_donors": [d.model_dump() for d in top_donors[:8]],
        "top_organizations": [o.model_dump() for o in top_organizations[:5]],
        "superpac_activity": [s.model_dump() for s in superpac_activity[:5]],
    }

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_tokens=180,
            messages=[
                {"role": "system", "content": SUMMARY_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        "Write a short financial-record summary from this FEC data JSON:\n"
                        f"{payload}"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or fallback
    except Exception:
        return fallback


def _display_name(raw: str) -> str:
    if "," in raw:
        last, first = [part.strip() for part in raw.split(",", 1)]
        return f"{first.title()} {last.title()}"
    return raw.title() if raw.isupper() else raw


PAC_SUMMARY_SYSTEM = """You write short, neutral summaries of PAC giving for a Chrome extension.
Rules:
- Exactly 2–3 sentences.
- Use only provided numbers.
- Mention the cycle, giving to Democrats vs Republicans if available, and one top politician recipient if present.
- No speculation about influence or corruption.
- Lead with the PAC name."""


def rule_based_pac_summary(
    pac: PacSummary,
    cycle: int,
    totals: FinancialTotals | None,
    party: PartyBreakdown | None,
    gifts: list[PoliticianGift],
) -> str:
    name = _titleish(pac.name)
    type_label = pac.committee_type_full or "PAC"
    if not party and not totals:
        return (
            f"{name} ({type_label}) has limited FEC giving data for the {cycle} cycle. "
            "Try another election cycle."
        )

    parts: list[str] = []
    if party:
        parts.append(
            f"{name} directed {format_money(party.democratic)} to Democratic committees "
            f"and {format_money(party.republican)} to Republican committees in the {cycle} cycle, "
            f"based on itemized Schedule B gifts sampled from FEC filings."
        )
    elif totals:
        parts.append(
            f"{name} reported {format_money(totals.fed_candidate_committee_contributions or totals.disbursements)} "
            f"in federal candidate/committee activity during the {cycle} cycle."
        )

    if gifts:
        lead = gifts[0]
        party_bit = f" ({lead.party})" if lead.party else ""
        parts.append(
            f"Its largest sampled political recipient was {lead.name}{party_bit} "
            f"at {format_money(lead.total)}."
        )
    if totals and len(parts) < 3:
        parts.append(
            f"Overall, the committee reported {format_money(totals.receipts)} in receipts "
            f"and {format_money(totals.disbursements)} in disbursements."
        )
    return " ".join(parts[:3])


async def generate_pac_summary(
    pac: PacSummary,
    cycle: int,
    totals: FinancialTotals | None,
    party: PartyBreakdown | None,
    party_history: list[PartyBreakdown],
    gifts: list[PoliticianGift],
) -> str:
    fallback = rule_based_pac_summary(pac, cycle, totals, party, gifts)
    if not settings.openai_api_key:
        return fallback

    payload = {
        "pac": pac.model_dump(),
        "cycle": cycle,
        "totals": totals.model_dump() if totals else None,
        "party_breakdown": party.model_dump() if party else None,
        "party_history": [p.model_dump() for p in party_history[:4]],
        "politician_gifts": [g.model_dump() for g in gifts[:8]],
    }
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.2,
            max_tokens=180,
            messages=[
                {"role": "system", "content": PAC_SUMMARY_SYSTEM},
                {
                    "role": "user",
                    "content": f"Write a short PAC giving summary from this FEC data JSON:\n{payload}",
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or fallback
    except Exception:
        return fallback


def _titleish(value: str) -> str:
    return value.title() if value.isupper() else value
