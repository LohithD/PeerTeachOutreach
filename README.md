# PeerTeach Outreach Pipeline

Automated pipeline that finds California middle schools, pulls each district's official LCAP from CDE, analyzes the entire PDF with Claude (text + tables + images), extracts the strongest PeerTeach outreach angles, enriches each admin with email + LinkedIn, drafts a personalized email, and writes everything to a Google Sheet.

Built for [PeerTeach](https://peerteach.com) — a Stanford-based math peer tutoring program for grades 3-9.

## How it works

```
   CDE School Directory (TSV)
            │
            ▼
   Filter to active middle schools  ──►  Master Google Sheet (one row per school)
            │
            ▼
   For each pending row:
     │
     ├─► Fetch LCAP from CDE API by district CDS code
     │       (fallback: Firecrawl Search if CDE has no record)
     │
     ├─► Send PDF to Claude → structured outreach angles (ranked 1-3)
     │       (large LCAPs split into 50-page chunks, results merged)
     │
     ├─► Firecrawl Search for admin's LinkedIn + email
     │
     ├─► Claude drafts a personalized email using the #1 angle
     │
     └─► Write everything back to that row in the sheet
```

## Project structure

```
PeerTeachOutreach/
├── main.py                  # Orchestrator (--populate, --batch N)
├── config.py                # Loads .env, defines paths + constants
├── requirements.txt
├── .env                     # API keys (NEVER committed)
├── service_account.json     # Google service account key (NEVER committed)
├── steps/
│   ├── find_schools.py      # Read CDE TSV, filter to middle schools
│   ├── find_lcaps.py        # CDE API + Firecrawl fallback
│   ├── analyze_lcap.py      # Claude PDF analysis with chunking
│   ├── find_admins.py       # Firecrawl-based LinkedIn + email lookup
│   ├── write_email.py       # Claude generates personalized email
│   └── sheet_sync.py        # Master sheet read/write (gspread)
└── data/                    # Cached CDE directory + LCAP PDFs (gitignored)
```

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### One-time: download the CDE school directory

CDE blocks automated downloads (Radware bot protection). Download once manually:
1. Open in a browser: `https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt`
2. Save the file as `data/ca_schools.txt`

### Configure API keys (`.env`)

```
FIRECRAWL_API_KEY=fc-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_SHEET_ID=<long ID from your sheet's URL>
GOOGLE_SERVICE_ACCOUNT_JSON=service_account.json
```

### Set up Google Sheets access

1. Create a Google Cloud project, enable the **Google Sheets API** + **Google Drive API**
2. Create a service account, download its JSON key as `service_account.json` in the project root
3. Create a Google Sheet, share it with the service account's `client_email` (Editor access)
4. Copy the sheet ID from the URL into `.env`

## Usage

**One-time populate** (fills sheet with ~1,366 active CA middle schools as `pending`):
```bash
.venv/bin/python main.py --populate
```

**Process the next N pending rows** (run on a schedule):
```bash
.venv/bin/python main.py --batch 10
.venv/bin/python main.py --batch 50
```

Each run pulls the next N pending rows from the sheet, processes them, writes results back, and marks the rows `done`. Safe to interrupt and resume — the script picks up wherever the sheet leaves off.

## Scheduling

Add to crontab (`crontab -e`) for hourly batches:
```
0 * * * * cd /path/to/PeerTeachOutreach && .venv/bin/python main.py --batch 50 >> run.log 2>&1
```

## Output (Google Sheet columns)

| Column | Description |
|---|---|
| status | `pending` / `done` / `failed` |
| cds_code | CDE's 14-digit school ID |
| school, district, county, city | From CDE directory |
| admin_name | Principal from CDE |
| admin_email, admin_phone, admin_linkedin | Enriched via Firecrawl |
| school_website | From CDE |
| lcap_year, lcap_url, lcap_source | `cde` or `firecrawl` |
| top_angles | Top 3 ranked angles, each with evidence and fit |
| key_metrics | Specific math-related figures from LCAP |
| stated_priorities | District goals relevant to PeerTeach |
| warning_flags | Reasons this might NOT be a fit |
| last_processed | ISO timestamp |
| notes | Reserved for manual notes |
| email_1 | Personalized cold email drafted from the #1 angle |

## The CDE API discovery

The pipeline initially used Firecrawl Search to guess each district's LCAP location. Inspection of the public California School Dashboard revealed an undocumented backend API that returns submitted LCAPs by district CDS code:

```
https://api.mycdeconnect.org/reports/lcap?cdsCode={DISTRICT_CDS}&year={YEAR}
```

This is the API the Dashboard's frontend uses to serve "Download LCAP" links. It returns the official PDF the district submitted to the state. The pipeline uses this as the primary source, with Firecrawl Search as a fallback for rare cases where the API has no record.

## Notes

- **Rate limits**: Anthropic's tier controls how fast the pipeline runs. Tier 1 (~30k input tokens/min) struggles with large LCAPs; Tier 4 (~450k/min) processes them with no waiting. See `console.anthropic.com/settings/limits`.
- **District-level caching**: LCAPs are cached per district CDS, so multiple middle schools in the same district share the same analysis (no duplicate API spend).
- **PDF caching**: Downloaded LCAPs are saved to `data/lcaps/` keyed by URL hash. Re-runs reuse the file.

## License

MIT
