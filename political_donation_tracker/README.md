# Political Donation Tracker

Chrome extension + local FastAPI backend that pulls federal campaign-finance data from the [FEC OpenFEC API](https://api.open.fec.gov/developers/) and uses an LLM to write a **short financial-record summary** for each politician.

## Features

- Search federal candidates **or PACs**
- Sort donors by amount or name
- Filter politician donor types: individuals, PACs/committees, Super PAC independent expenditures, organizations (employer totals)
- For PACs: giving by party (Dem vs Rep), donations to individual politicians, optional prior-cycle history
- Rank organizations by donated totals
- **LLM short financial/giving summary** (2–3 sentences) — OpenAI when `OPENAI_API_KEY` is set, otherwise rule-based from the same FEC data

## Setup

### 1. Backend

```bash
cd backend
python -m pip install -r requirements.txt
copy .env.example .env
```

Edit `.env`:

- `FEC_API_KEY` — free key from https://api.data.gov/signup/ (`DEMO_KEY` works for light testing)
- `OPENAI_API_KEY` — optional; enables LLM summaries via `gpt-4o-mini`

Start the API from the project root:

```bash
python main.py
```

API: http://127.0.0.1:8000  
Docs: http://127.0.0.1:8000/docs

### 2. Chrome extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select the `extension/` folder
4. Click the extension icon, search a politician, open their profile

Keep `python main.py` running while using the extension.

## Notes

- Super PACs generally do **not** give directly to candidates. The Super PAC view shows independent expenditures supporting or opposing the candidate.
- Organization rankings come from itemized individual contributions grouped by employer.
- Contributor lists from FEC data may not be used for commercial solicitation.
