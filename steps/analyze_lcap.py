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

ANALYSIS_PROMPT = """You are analyzing a California school district's LCAP on behalf of Dr. Soren Rosier — a Stanford researcher who studies student collaboration in math and built PeerTeach.

Soren's expertise areas (he can credibly speak to ALL of these):
1. PEER MATH TUTORING — built PeerTeach, a structured peer-to-peer math program for grades 3-9 used during the school day
2. ADAPTIVE LEARNING / BLENDED LEARNING SOFTWARE — has spent much of his research career studying which math software actually works (DreamBox, ALEKS, ST Math, Khan Academy, i-Ready, Imagine Math, etc.) and has strong opinions on which ones move the needle
3. MIXED-ABILITY MATH CLASSROOMS — research on heterogeneous grouping, differentiation strategies
4. MATH DISCOURSE — how to get students explaining mathematical thinking aloud
5. STRETCHING TEACHER CAPACITY — student-led models that multiply what one teacher can deliver
6. MATH INTERVENTION DURING THE SCHOOL DAY — Tier 2/3 intervention design, especially for grades 3-9

Your job: read the LCAP carefully and find the THREE strongest angles where the DISTRICT'S SPECIFIC APPROACH to a math problem overlaps with SOREN'S SPECIFIC EXPERTISE.

CRITICAL FRAMING SHIFT:
Do NOT just identify gaps ("students are X points below standard"). Identify what the district says it is DOING about those gaps — the specific strategies, programs, tools, software, intervention models, staffing structures, or budget allocations they describe. THEN match those specific approaches to Soren's expertise.

Examples of strong angles (the pattern to follow):

Weak (gap-focused, generic): "EL students are 113 pts below standard in math"
Strong (approach-focused, specific): "District is using blended learning in mixed-ability classrooms for EL math support — Soren has studied many adaptive math platforms and can share which ones work for ELs"

Weak: "Math achievement is low"
Strong: "District purchased ST Math for grades 4-8 (Action 2.3, $180K) to address foundational gaps — Soren has researched ST Math specifically and has thoughts on supplementing it with peer discourse"

Weak: "They care about Tier 2 intervention"
Strong: "District is staffing 2 intervention coaches per site for Tier 2 math (Action 3.4) — Soren has specific opinions on how peer-led models extend coach capacity without doubling staff"

DIG IN. The strongest angles come from concrete specifics in the LCAP:
- WHAT software/platform/curriculum did they buy or name?
- WHAT intervention model are they using (pullout, push-in, after-school, blended)?
- WHAT staffing structure (coaches, intervention specialists, paraprofessionals, tutoring vendors)?
- WHAT instructional strategy (small groups, station rotation, discourse-focused, project-based)?
- WHAT vendor or program (Carnegie, AVID, MTSS framework, specific tutoring service)?

If the LCAP names a specific tool, vendor, or method — that IS the angle. The match to Soren's expertise comes from his deep knowledge of those exact tools/methods.

Strict exclusions (do not use as angles):
- Anything about literacy or reading
- Anything outside grade 3-9 (e.g. K-2, high-school-only, TK)
- General SEL, attendance, or climate work
- Pure budget categories with no described approach
- Vague goals ("close gaps", "support all students") with no described strategy

Evidence rules:
- Every angle must cite a direct quote, figure, page, or action number from the LCAP
- Do NOT invent that Soren has used or evaluated something. He has broad knowledge of common math platforms and intervention models; only claim familiarity with what's plausibly in the public research literature on common K-12 tools.
- Do NOT generalize about what districts usually do — only what THIS district says it does

Return ONLY valid JSON. Keep every field SHORT and SCANNABLE — this is read at a glance, not studied.

Length rules (hard):
- angle: max 12 words, one short sentence, no commas, no clauses
- evidence: max 20 words, a tight quote or figure (with page if visible)
- why_it_lands: max 12 words, one short sentence
- each key_metric: max 10 words, just a number + what it measures
- each stated_priority: max 8 words, a short noun phrase
- each warning_flag: max 12 words, one tight clause

Strip filler. No "the district is focused on", no "PeerTeach can help", no marketing voice. Just the facts.

Return shape (every angle must include district_approach AND soren_expertise):
{
  "district_name": "...",
  "lcap_year": "2024-25",
  "top_angles": [
    {
      "rank": 1,
      "district_approach": "Using ST Math + small-group pullout for grades 4-8 math intervention (Action 2.3, $180K, p.45)",
      "soren_expertise": "Has researched ST Math specifically — knows where it underperforms on word problems and discourse",
      "angle": "Ask about their ST Math results vs. peer discourse supplement",
      "strength": "strong"
    },
    { "rank": 2, "district_approach": "...", "soren_expertise": "...", "angle": "...", "strength": "..." },
    { "rank": 3, "district_approach": "...", "soren_expertise": "...", "angle": "...", "strength": "..." }
  ],
  "key_metrics": ["Math SBAC: 38% met standard 2023-24"],
  "stated_priorities": ["ST Math grades 4-8", "Tier 2 small-group pullout", "LTEL math support"],
  "warning_flags": ["already using peer tutoring vendor (BAYAC)", "...or empty list"]
}

Length rules (hard):
- district_approach: max 25 words — WHAT they're doing + program/tool/vendor name + page/action ref
- soren_expertise: max 20 words — WHY Soren can credibly speak to that specific approach
- angle: max 12 words — a one-line opening for the email
- key_metric / stated_priority / warning_flag: max 10 words each

Always return exactly 3 angles, ranked. Strongest first."""


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
            # dedupe on district_approach first (more specific than angle text)
            key = (angle.get("district_approach") or angle.get("angle") or "").lower()[:100]
            if key and key not in seen_angles:
                seen_angles.add(key)
                candidates.append(angle)
        for k in ("key_metrics", "stated_priorities", "warning_flags"):
            for item in (a.get(k) or []):
                if item not in merged[k]:
                    merged[k].append(item)

    # cap merged lists to keep columns scannable
    merged["key_metrics"] = merged["key_metrics"][:6]
    merged["stated_priorities"] = merged["stated_priorities"][:6]
    merged["warning_flags"] = merged["warning_flags"][:5]

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
