"""Step 4.5: Generate a personalized outreach email for a district using the
top angle extracted from its LCAP.

Soren Rosier (Stanford researcher, PeerTeach developer) writes these to
school district leaders. The email is short, restrained, and conversational —
not marketing copy.
"""
import anthropic
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

EMAIL_PROMPT_TEMPLATE = """You are Soren Rosier writing a short outreach email. Follow the template below closely. Use the recipient's first name only.

About Soren (he can credibly speak to ALL of these):
- Researcher at Stanford studying student collaboration in math
- Used to teach and struggled himself with the very challenges his research now addresses
- Has spent the past decade working with many middle schools
- Built PeerTeach, a structured peer math program for grades 3-9 (students coach each other during the school day)
- Has spent much of his research career studying adaptive/blended learning math software (knows the major platforms and what works)
- Researches mixed-ability classrooms, math discourse, and stretching teacher capacity through student-led models

Recipient:
- First name: {first_name}
- District: {district_name}
- School: {school}

The single strongest angle for this email (from the district's LCAP):

District's specific approach: {district_approach}
Why Soren can speak to it: {soren_expertise}
Email angle: {angle}

Follow this exact structure (4 short paragraphs + signoff). The email must reference the district's SPECIFIC approach (not just the gap), and Soren's response must come from his SPECIFIC expertise area on that approach. Keep the casual voice and rhythm.

---
Hey {first_name},

I noticed from your LCAP that {district_name} is [reference their SPECIFIC approach — name the tool, program, model, or staffing structure they described, in 1 sentence].

What I've found working with many middle schools the past decade is [Soren's specific observation about that approach drawn from his expertise, in 1 sentence]. [Optionally: 1 short sentence with a concrete thought, observation, or question about that approach — not a sales line].

I'm Soren Rosier, I'm a researcher from Stanford. I used to teach and I really struggled myself with [a relatable version of the same challenge]. It actually drove a lot of the research I've done here.

How are you [a specific, curious question about their implementation of that approach — not a generic "how are you improving math"]? If you're not too busy the next week or two, I'd love to trade notes and share some of the stuff we've been building. I think you might find it really interesting.

-Soren
---

Key shifts from generic outreach:
- NEVER say "improve math achievement", "close gaps", "support struggling students" without naming the SPECIFIC method
- DO name their specific tool / vendor / strategy / program (the district_approach above)
- DO let Soren speak as someone who has researched that specific thing — not as a PeerTeach salesperson
- The 2nd paragraph should sound like Soren noticed something interesting about THEIR specific approach, not like he's pitching
- The closing question should be a real curious question about how they're implementing the approach, not a sales lead-in

Hard rules:
- NO em dashes (—) or en dashes (–) anywhere
- NO antithesis grammar like "not X, but Y" or "X, not Y" or "It's not just A, it's B"
- NO sales-y or excited language
- NO buzzwords: "transform", "revolutionary", "scalable", "leverage", "innovative", "cutting-edge"
- NO AI-tell phrases: "I hope this finds you well", "I hope you're doing well", "Furthermore", "Moreover", "In conclusion", "delve", "tapestry", "robust"
- NO em-dash-style asides
- NO generic praise like "your district is doing amazing work"
- NO placeholders or brackets in the final output
- NO mention of literacy, reading, ELA
- Don't invent specifics about Soren's background beyond what is listed above
- Don't claim specific results or numbers Soren has achieved
- Don't mention specific grades, subjects, or years he taught
- Don't quote dollar amounts from the LCAP — keep it conversational, not data-heavy
- Match the casual tone in the template ("really focused on", "I'd love to", "the stuff we've been building")
- Keep sentences medium-length and varied — avoid the AI rhythm of equal-length clauses
- Use commas, parentheses, or two separate sentences instead of dashes

Output:
Return ONLY the email body. Start with "Hey {first_name},". End with "-Soren". No preamble, no subject line, no quotes around the email."""


def _scrub_dashes(text):
    """Strip em/en dashes per the user's hard rule."""
    return text.replace("—", ", ").replace("–", ", ")


def generate_email(admin_name, title, district_name, school, top_angle):
    """Generate a personalized email using the #1 angle. Returns email text or empty string."""
    if not top_angle or not top_angle.get("angle"):
        return ""

    first_name = (admin_name or "").split()[0] or "there"

    prompt = EMAIL_PROMPT_TEMPLATE.format(
        first_name=first_name,
        district_name=district_name or "your district",
        school=school or "",
        angle=top_angle.get("angle", ""),
        district_approach=top_angle.get("district_approach", ""),
        soren_expertise=top_angle.get("soren_expertise", ""),
    )

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}],
    )
    return _scrub_dashes(msg.content[0].text.strip())


if __name__ == "__main__":
    sample = {
        "angle": "You're investing LREBG funds in tutoring to close math gaps — PeerTeach can help scale 1:1 support without adding adult staff",
        "evidence": "Action 3.3 2025-26: extended learning opportunities will be provided through tutoring for students who need academic support",
        "why_it_lands": "PeerTeach scales peer-to-peer math tutoring during the school day without requiring additional certificated staff",
    }
    out = generate_email("Dave Trejo", "Principal",
                         "Los Angeles County Office of Education",
                         "Environmental Charter Middle - Gardena",
                         sample)
    print(out)
