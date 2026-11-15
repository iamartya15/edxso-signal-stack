"""Adaptive interview: exactly 10 questions, generated per company.

Questions are assembled from what the research actually found (or failed
to find) about *this* company - its sector, the offerings named on its
own website, whether competitors/goals are already known, and so on.
Two different companies therefore get visibly different interviews.
Answers to the tagged questions (goals / competitors / customers /
products) flow back into the editable company profile.
"""

PROFILE_FIELDS = ("goals", "competitors", "customers", "products")


def _offerings(company, research_items):
    """Offerings named in verified homepage headings, if any."""
    found = []
    for item in research_items:
        if item["label"] == "VERIFIED FACT" and item["text"].startswith("Homepage heading:"):
            found.append(item["text"].split('"')[1] if '"' in item["text"] else "")
    return [f for f in found if f][:3]


def generate_questions(company, research_items):
    name = company["name"]
    sector = company.get("sector") or "your sector"
    offerings = _offerings(company, research_items)
    competitors_known = bool((company.get("competitors") or "").strip())
    goals_known = bool((company.get("goals") or "").strip())
    lead_offering = offerings[0] if offerings else (company.get("products") or "your main offering")

    qs = []
    # 1 - always: goals (drives relevance ranking)
    qs.append({
        "field": "goals",
        "question": f"What are {name}'s top 3 business goals for the next two quarters? "
                    f"(These goals drive how every signal is ranked for you.)",
        "known": goals_known,
    })
    # 2 - offerings, referencing what the website itself says
    if offerings:
        qs.append({
            "field": "products",
            "question": f"Your homepage highlights \"{lead_offering}\". Which of your offerings "
                        f"({'; '.join(offerings)}) matters most commercially right now, and are any missing from the site?",
            "known": bool(company.get("products")),
        })
    else:
        qs.append({
            "field": "products",
            "question": f"We could not extract a clear product list from {name}'s website. "
                        "List your main products/services in priority order.",
            "known": bool(company.get("products")),
        })
    # 3 - customers, sector-aware wording
    sector_customer = {
        "Education": "students and parents",
        "Consumer Electronics": "online shoppers",
        "SaaS / Software": "business buyers and their IT teams",
    }.get(sector, "customers")
    qs.append({
        "field": "customers",
        "question": f"Who exactly buys from {name} today - which segment of {sector_customer} "
                    "converts best, and where do they usually discover you?",
        "known": bool(company.get("customers")),
    })
    # 4 - competitors: confirm or discover
    if competitors_known:
        qs.append({
            "field": "competitors",
            "question": f"You listed these competitors: {company['competitors']}. "
                        "Which one worries you most right now, and why?",
            "known": True,
        })
    else:
        qs.append({
            "field": "competitors",
            "question": f"Which 2-4 companies does {name} most often lose customers to in {sector}? "
                        "(Names you give here become tracked competitor sources.)",
            "known": False,
        })
    # 5 - sector-specific risk
    sector_risk = {
        "Education": "admission cycles, visa/policy changes or exam calendar shifts",
        "Consumer Electronics": "festive-season discount wars, component prices or marketplace policy changes",
        "SaaS / Software": "a global incumbent cutting prices, or a platform/API change you depend on",
    }.get(sector, "a sudden regulatory, pricing or platform change")
    qs.append({
        "field": "",
        "question": f"What external event would hurt {name} fastest - for example {sector_risk}? "
                    "Which of these should the brief flag at High priority?",
        "known": False,
    })
    # 6 - customer voice
    qs.append({
        "field": "",
        "question": f"Where do {name}'s customers complain or praise you publicly "
                    "(reviews, social media, forums)? Those places become Customers-category sources.",
        "known": False,
    })
    # 7 - internal sources
    qs.append({
        "field": "",
        "question": f"Which of {name}'s own channels should rivals never beat you to - "
                    "blog, press releases, product updates, careers page? We monitor these as Internal signals.",
        "known": False,
    })
    # 8 - decision cadence -> scheduling
    qs.append({
        "field": "",
        "question": f"Who reads the Monday Morning Brief at {name}, and what decision does it feed "
                    "(pricing, marketing spend, product roadmap)?",
        "known": False,
    })
    # 9 - geography / expansion, tied to location if known
    if company.get("location"):
        qs.append({
            "field": "",
            "question": f"You operate from {company['location']}. Are you expanding to new geographies "
                        "or segments this year that monitoring should watch?",
            "known": True,
        })
    else:
        qs.append({
            "field": "",
            "question": f"Which cities/countries does {name} sell in today, and where do you plan "
                        "to expand? (Sets the geography of market sources.)",
            "known": False,
        })
    # 10 - noise control, references the lead offering again
    qs.append({
        "field": "",
        "question": f"What should Signal Stack NEVER bother you with - topics around "
                    f"\"{lead_offering}\" or {sector} that look relevant but are noise for {name}?",
        "known": False,
    })
    assert len(qs) == 10, "the interview must contain exactly 10 questions"
    return qs
