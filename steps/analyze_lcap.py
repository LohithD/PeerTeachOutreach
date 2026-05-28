"""Step 3: Download LCAP PDF and analyze with Claude API (text + images).

Claude's document content block reads the full PDF including charts, tables,
and embedded images — no manual PDF parsing needed.
"""
import base64
import hashlib
import io
import json
import re
import time
import requests
import anthropic
from pypdf import PdfReader, PdfWriter
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, PDF_DIR

MAX_PAGES_PER_CALL = 50  # bumped from 30 — higher-tier accounts have headroom for bigger chunks

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

ANALYSIS_PROMPT = """You are analyzing a California school district's LCAP (Local Control and Accountability Plan) on behalf of PeerTeach.

PeerTeach context:
- Stanford-based math peer tutoring program for grades 3-9
- Helps students coach one another in math through structured peer learning activities during the school day
- Built by Dr. Soren Rosier, a Stanford researcher focused on student collaboration in math

Your job: read the entire LCAP — including tables, charts, dollar amounts, and embedded images — and identify the THREE strongest PeerTeach-relevant outreach angles for this district, ranked from strongest to weakest.

What counts as a strong angle:
The angle must connect a SPECIFIC priority, challenge, action, or budget item in this LCAP to one of these PeerTeach-relevant themes:
- student-to-student math discourse
- structured peer collaboration in math
- math intervention during the school day (esp. grades 3-9)
- making tutoring feasible without major staffing demands
- increasing math confidence
- supporting MTSS or Tier 2 math intervention
- helping students explain their mathematical thinking
- teacher capacity challenges (not enough adults to deliver intervention)
- academic recovery in math
- scalable student support during the school day

What does NOT count as a strong angle:
- Generic goals that could apply to any district ("improve math achievement", "support all students", "close achievement gaps") UNLESS paired with a specific implementation challenge
- Anything about literacy or reading
- General SEL, climate, or attendance work unless it explicitly ties to math discourse / peer learning / Tier 2 academic intervention
- Anything outside the grade 3-9 band (e.g. high-school-only initiatives, TK programs)
- Broad budget categories without specific intent

The strongest angle is the one with the most concrete overlap between THIS district's stated priorities and PeerTeach's core offering. If something unique about the district makes it an especially strong fit (e.g., they explicitly call out peer learning, or have allocated specific funds for in-school math tutoring), that should be #1.

Evidence rules:
- Every angle must cite a direct quote or specific figure from the LCAP — page number if visible
- Do NOT invent facts. If the LCAP doesn't say something, don't claim it
- Do NOT generalize about what districts "usually" care about — only what THIS district says

Return ONLY valid JSON. Keep every field SHORT and SCANNABLE — this is read at a glance, not studied.

Length rules (hard):
- angle: max 12 words, one short sentence, no commas, no clauses
- evidence: max 20 words, a tight quote or figure (with page if visible)
- why_it_lands: max 12 words, one short sentence
- each key_metric: max 10 words, just a number + what it measures
- each stated_priority: max 8 words, a short noun phrase
- each warning_flag: max 12 words, one tight clause

Strip filler. No "the district is focused on", no "PeerTeach can help", no marketing voice. Just the facts.

Return shape:
{
  "district_name": "...",
  "lcap_year": "2024-25",
  "top_angles": [
    {
      "rank": 1,
      "angle": "LTEL students 90 pts below math standard",
      "evidence": "Action 1.10: $100K LTEL math support (p.41)",
      "why_it_lands": "Peer math discourse builds language + math",
      "strength": "strong"
    },
    { "rank": 2, "angle": "...", "evidence": "...", "why_it_lands": "...", "strength": "..." },
    { "rank": 3, "angle": "...", "evidence": "...", "why_it_lands": "...", "strength": "..." }
  ],
  "key_metrics": ["Math SBAC: 38% met standard 2023-24", "Chronic absenteeism: 18.4%"],
  "stated_priorities": ["Tier 2 math intervention", "LTEL support", "Expanded learning"],
  "warning_flags": ["already using peer tutoring vendor", "...or empty list"]
}

Use the example above as a length and tone guide. Adapt the content to THIS district. Always return exactly 3 angles, ranked."""


def _pdf_path_for(url):
    h = hashlib.md5(url.encode()).hexdigest()[:12]
    return PDF_DIR / f"{h}.pdf"


def download_pdf(url):
    path = _pdf_path_for(url)
    if path.exists() and path.stat().st_size > 1000:
        return path
    print(f"[lcap] Downloading {url}")
    resp = requests.get(url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    if b"%PDF" not in resp.content[:1024]:
        raise ValueError(f"Not a PDF: {url}")
    path.write_bytes(resp.content)
    return path


def save_pdf_bytes(pdf_bytes, cache_key):
    """Persist PDF bytes already fetched by find_lcaps."""
    h = hashlib.md5(cache_key.encode()).hexdigest()[:12]
    path = PDF_DIR / f"{h}.pdf"
    if not path.exists() or path.stat().st_size < 1000:
        path.write_bytes(pdf_bytes)
    return path


def _split_pdf_to_chunks(pdf_path, max_pages=MAX_PAGES_PER_CALL):
    """Yield base64-encoded PDF chunks of <= max_pages each."""
    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    if total <= max_pages:
        yield base64.standard_b64encode(pdf_path.read_bytes()).decode("utf-8"), 1, total
        return
    print(f"[lcap] PDF has {total} pages — splitting into chunks of {max_pages}")
    for start in range(0, total, max_pages):
        end = min(start + max_pages, total)
        writer = PdfWriter()
        for i in range(start, end):
            writer.add_page(reader.pages[i])
        buf = io.BytesIO()
        writer.write(buf)
        yield base64.standard_b64encode(buf.getvalue()).decode("utf-8"), start + 1, end


_STRENGTH_RANK = {"strong": 0, "medium": 1, "weak": 2}


def _merge_analyses(analyses):
    """Combine per-chunk analyses into one. Always emit exactly 3 angles, ranked.
    Sort all candidate angles by (strength, original rank) and renumber 1/2/3."""
    merged = {
        "district_name": "",
        "lcap_year": "",
        "top_angles": [],
        "key_metrics": [],
        "stated_priorities": [],
        "warning_flags": [],
    }
    seen_angles = set()
    candidates = []
    for a in analyses:
        if not isinstance(a, dict) or "error" in a:
            continue
        if not merged["district_name"] and a.get("district_name"):
            merged["district_name"] = a["district_name"]
        if not merged["lcap_year"] and a.get("lcap_year"):
            merged["lcap_year"] = a["lcap_year"]
        for angle in (a.get("top_angles") or []):
            key = (angle.get("angle") or "").lower()[:80]
            if key and key not in seen_angles:
                seen_angles.add(key)
                candidates.append(angle)
        for k in ("key_metrics", "stated_priorities", "warning_flags"):
            for item in (a.get(k) or []):
                if item not in merged[k]:
                    merged[k].append(item)

    candidates.sort(key=lambda a: (
        _STRENGTH_RANK.get((a.get("strength") or "weak").lower(), 3),
        a.get("rank", 99),
    ))
    top3 = candidates[:3]
    for i, a in enumerate(top3, start=1):
        a["rank"] = i
    merged["top_angles"] = top3
    return merged


def analyze_pdf(pdf_path):
    chunks = list(_split_pdf_to_chunks(pdf_path))
    analyses = []
    for pdf_b64, start, end in chunks:
        if len(chunks) > 1:
            print(f"[lcap] Analyzing pages {start}-{end} of {chunks[-1][2]}")
        analyses.append(_analyze_chunk(pdf_b64))
        if len(chunks) > 1:
            time.sleep(2)
    if len(analyses) == 1:
        return analyses[0]
    return _merge_analyses(analyses)


def _analyze_chunk(pdf_b64):
    def _call():
        return client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": ANALYSIS_PROMPT},
                ],
            }],
        )

    # retry on rate limits (Anthropic free tier: 30k input tokens/min)
    for attempt in range(4):
        try:
            msg = _call()
            break
        except anthropic.RateLimitError as e:
            wait = 65 * (attempt + 1)
            print(f"[lcap] Rate limited (attempt {attempt+1}/4). Waiting {wait}s. "
                  f"Upgrade your Anthropic tier for faster runs.")
            time.sleep(wait)
    else:
        raise RuntimeError("Rate limited after 4 retries — upgrade Anthropic tier")
    raw = msg.content[0].text.strip()
    # strip ```json fences if model added them
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # try to find a JSON object in the response
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return {"error": "could not parse JSON", "raw": raw[:500]}


def analyze_lcap_url(url):
    pdf_path = download_pdf(url)
    return analyze_pdf(pdf_path)


if __name__ == "__main__":
    import sys
    url = sys.argv[1]
    result = analyze_lcap_url(url)
    print(json.dumps(result, indent=2))
