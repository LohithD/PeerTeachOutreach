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
Peer-teaching insight Soren has about that approach: {peer_teaching_insight}
Email angle: {angle}

Follow this exact structure (4 short paragraphs + signoff). The email must reference the district's SPECIFIC approach AND must explicitly anchor to PEER TEACHING in both the middle paragraph and the closing question. Soren's product (PeerTeach) is about students teaching/coaching/explaining math to each other — that is the through-line of the whole email.

---
Hey {first_name},

I noticed from your LCAP that {district_name} is [reference their SPECIFIC approach — name the tool, program, model, or staffing structure they described, in 1 sentence].

What I've found in my research is [a specific observation about that approach + an explicit peer-teaching dimension — e.g., where the approach is strong individually but weak on student-to-student interaction, or where peer coaching extends what the approach can do]. [Optionally: 1 short sentence that goes deeper on the peer-teaching connection — what students explaining math to each other adds to what they're already doing].

I'm Soren Rosier, I'm a researcher from Stanford. I used to teach and I really struggled myself with [a relatable version of the same challenge — frame around getting students to talk to each other about math, or watching kids stay quiet, or kids only learning from the teacher's voice]. It actually drove a lot of the research I've done here.

[A specific, curious question that explicitly involves peer teaching — e.g., "How are you building student-to-student explanation into..." or "Have you seen kids coaching each other through..." or "What's the dynamic like when students try to work through this together..." — NEVER a generic "how are you improving math"]. If you're not too busy the next week or two, I'd love to trade notes and share some of the stuff we've been building. I think you might find it really interesting.

-Soren
---

Hard rules for the writing:
- Middle paragraph MUST explicitly name peer teaching / students explaining to each other / peer coaching / student-to-student discourse — not just generic "research"
- Closing question MUST explicitly involve students teaching, coaching, or explaining math to each other
- Soren's "struggle" line MUST be peer-teaching adjacent (getting kids to talk to each other about math, the silence in math classrooms, etc.) — NOT generic "supporting all students"
- NEVER write a paragraph where you could swap out PeerTeach for a different ed-tech product and the email still works. Every paragraph needs the peer-teaching signature.
- Do NOT say "improve math achievement", "close gaps", "support struggling students" as the only framing — always pair with the specific peer-teaching mechanism
- The tone is curious researcher, not pitch
- No em dashes, no antithesis grammar, no buzzwords

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
        peer_teaching_insight=top_angle.get("peer_teaching_insight", top_angle.get("soren_expertise", "")),
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
