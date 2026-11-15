"""Signal Stack builder: discovers and proposes intelligence sources.

Source discovery criteria (also documented in docs/TECHNICAL.md):

INCLUDE a source when it is
  * public and fetchable without login or payment,
  * topically tied to the company, a named competitor, its customers or
    its sector,
  * updated at least monthly (news feeds, active blogs, live sites), and
  * attributable - a real publisher or the company/competitor itself.

EXCLUDE: login-walled or paywalled pages, social profiles that block
crawlers, generic homepages with no topical link, dead feeds.

REMOVE (in the UI) when a source fails repeatedly, goes off-topic, or
duplicates another source's content.

Every proposed source carries its reason for inclusion and a crawl
frequency. RSS feeds discovered on the company's own site are verified
before they are added; constructed Google News RSS searches are used for
competitor / customer / market coverage because they are public, free
and always fetchable.
"""
from urllib.parse import quote_plus
import feedparser

from .research import normalise_url

GOOGLE_NEWS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def gnews(query):
    return GOOGLE_NEWS.format(q=quote_plus(query))


def verify_feed(url):
    """True if the URL currently parses as a feed with at least 1 entry."""
    try:
        parsed = feedparser.parse(url)
        return len(getattr(parsed, "entries", []) or []) > 0
    except Exception:
        return False


def build_stack(company, feeds_found):
    """Return a list of source dicts for this company (not yet stored)."""
    name = company["name"]
    sector = company.get("sector") or "business"
    website = normalise_url(company["website"])
    out = []

    # ---- Internal: the company's own voice -------------------------------
    own_feed = feeds_found[0] if feeds_found else None
    if own_feed:
        out.append({
            "name": f"{name} - official feed", "url": own_feed,
            "category": "Internal", "source_type": "rss", "authority": 90,
            "frequency_hours": 12,
            "reason": "First-party announcements, straight from the company itself.",
        })
    out.append({
        "name": f"{name} - website watch", "url": website,
        "category": "Internal", "source_type": "webpage", "authority": 85,
        "frequency_hours": 24,
        "reason": "Detects changes to the company's own homepage messaging, offers and positioning.",
    })

    # ---- Market: coverage of the company and its sector ------------------
    out.append({
        "name": f"{name} - news coverage", "url": gnews(f'"{name}"'),
        "category": "Market", "source_type": "rss", "authority": 65,
        "frequency_hours": 12,
        "reason": "Every public news mention of the company, via Google News RSS.",
    })
    out.append({
        "name": f"{sector} sector news", "url": gnews(f"{sector} industry India"),
        "category": "Market", "source_type": "rss", "authority": 60,
        "frequency_hours": 24,
        "reason": f"Policy, funding and demand shifts across the {sector} sector.",
    })

    # ---- Competitors: one news feed per named competitor -----------------
    competitors = [c.strip() for c in (company.get("competitors") or "").split(",")
                   if c.strip()]
    if competitors:
        for comp in competitors[:4]:
            out.append({
                "name": f"{comp} - competitor news", "url": gnews(f'"{comp}"'),
                "category": "Competitors", "source_type": "rss", "authority": 65,
                "frequency_hours": 12,
                "reason": f"Tracks launches, pricing, funding and partnerships of named competitor {comp}.",
            })
    else:
        out.append({
            "name": f"{sector} competitors watch", "url": gnews(f"{sector} startups funding launch India"),
            "category": "Competitors", "source_type": "rss", "authority": 55,
            "frequency_hours": 24,
            "reason": "Discovery feed until named competitors are added in the interview; "
                    "catches funded challengers entering the sector.",
        })

    # ---- Customers: the voice of the buyer -------------------------------
    customer_terms = {
        "Education": "students review experience",
        "Consumer Electronics": "review complaints users",
        "SaaS / Software": "review users pricing",
    }.get(sector, "review feedback customers")
    out.append({
        "name": f"{name} - customer voice", "url": gnews(f'"{name}" {customer_terms}'),
        "category": "Customers", "source_type": "rss", "authority": 55,
        "frequency_hours": 24,
        "reason": "Public reviews, feedback and complaints mentioning the company by name.",
    })
    out.append({
        "name": f"{sector} buyer trends", "url": gnews(f"{sector} customers demand trends India"),
        "category": "Customers", "source_type": "rss", "authority": 55,
        "frequency_hours": 24,
        "reason": "Demand-side shifts: what buyers in this sector want, spend on and switch for.",
    })
    return out
