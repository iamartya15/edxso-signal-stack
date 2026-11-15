"""Company research.

Fetches the company's public website with requests + BeautifulSoup and
turns what is *actually on the page* into profile research items. Every
item is labelled:

  VERIFIED FACT  - text taken from a named public source (the URL is stored)
  ASSUMPTION     - a clearly-marked inference made by Signal Stack itself

If the site cannot be fetched, the failure is reported and only the
assumptions (labelled as such) are produced - nothing is invented and
presented as fact.
"""
import re
import requests
from bs4 import BeautifulSoup

UA = {"User-Agent": "SignalStack/1.0 (research bot; +https://example.org/signalstack)"}
TIMEOUT = 12

SECTOR_KEYWORDS = {
    "Education": ["university", "universities", "study abroad", "students",
                  "admissions", "courses", "learning", "school", "college",
                  "exam", "tuition", "counselling", "counseling"],
    "Consumer Electronics": ["headphones", "earbuds", "smartwatch", "speaker",
                             "wearables", "gadgets", "audio"],
    "SaaS / Software": ["software", "saas", "platform", "cloud", "crm",
                        "automation", "apps for business", "subscription"],
    "Fintech": ["payments", "banking", "loans", "insurance", "fintech", "upi"],
    "Healthcare": ["health", "hospital", "clinic", "pharmacy", "diagnosis"],
    "E-commerce": ["shop", "store", "buy online", "delivery", "marketplace"],
}

SECTOR_ASSUMPTIONS = {
    "Education": [
        "Likely competes for students against larger, better-funded admission platforms (validate in the interview).",
        "Demand is probably seasonal around admission and exam cycles (validate in the interview).",
    ],
    "Consumer Electronics": [
        "Likely competes on price and online reviews against other D2C electronics brands (validate in the interview).",
        "Demand is probably seasonal around festive sales (validate in the interview).",
    ],
    "SaaS / Software": [
        "Likely sells on subscription with churn as a key risk (validate in the interview).",
        "Buyers probably compare it against global incumbents on price and support (validate in the interview).",
    ],
    "default": [
        "Market position and pricing are not yet verified from public sources (validate in the interview).",
        "Customer acquisition channels are not yet verified from public sources (validate in the interview).",
    ],
}


def normalise_url(website):
    website = (website or "").strip()
    if website and not website.startswith(("http://", "https://")):
        website = "https://" + website
    return website


def fetch_site(url):
    """Fetch and parse a page. Returns a dict; on failure {'error': ...}."""
    try:
        resp = requests.get(url, headers=UA, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        return {"error": f"could not fetch {url}: {exc.__class__.__name__}"}
    soup = BeautifulSoup(resp.text, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    desc = ""
    tag = soup.find("meta", attrs={"name": "description"}) or \
        soup.find("meta", attrs={"property": "og:description"})
    if tag and tag.get("content"):
        desc = tag["content"].strip()
    headings = []
    for h in soup.find_all(["h1", "h2"]):
        t = " ".join(h.get_text(" ").split())
        if 3 <= len(t) <= 120 and t not in headings:
            headings.append(t)
    paragraphs = []
    for p in soup.find_all("p"):
        t = " ".join(p.get_text(" ").split())
        if len(t) >= 60 and t not in paragraphs:
            paragraphs.append(t)
    feeds = []
    for link in soup.find_all("link", attrs={"type": re.compile("rss|atom", re.I)}):
        href = link.get("href")
        if href:
            feeds.append(requests.compat.urljoin(url, href))
    return {"title": title, "description": desc, "headings": headings[:14],
            "paragraphs": paragraphs[:6], "feeds": feeds, "final_url": resp.url}


def detect_sector(text):
    text = (text or "").lower()
    best, best_hits = "", 0
    for sector, words in SECTOR_KEYWORDS.items():
        hits = sum(1 for w in words if w in text)
        if hits > best_hits:
            best, best_hits = sector, hits
    return best if best_hits >= 2 else ""


def build_research(company_name, website):
    """Return (items, sector, feeds, error) for a company.

    items: list of dicts with label/text/source, ready to store.
    """
    url = normalise_url(website)
    page = fetch_site(url)
    items = []
    if page.get("error"):
        items.append({
            "label": "ASSUMPTION",
            "text": f"{company_name}'s website could not be fetched automatically, "
                    "so no public facts were verified in this run.",
            "source": "Signal Stack research run (fetch failed)",
        })
        for a in SECTOR_ASSUMPTIONS["default"]:
            items.append({"label": "ASSUMPTION", "text": a,
                          "source": "Signal Stack inference - not verified"})
        return items, "", [], page["error"]

    src = page["final_url"]
    if page["title"]:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Website title: {page['title']}", "source": src})
    if page["description"]:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Site description: {page['description']}", "source": src})
    for h in page["headings"][:8]:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Homepage heading: \"{h}\"", "source": src})
    for p in page["paragraphs"][:3]:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Homepage text: {p[:280]}", "source": src})
    if page["feeds"]:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Site publishes an RSS/Atom feed: {page['feeds'][0]}",
                      "source": src})

    corpus = " ".join([page["title"], page["description"]] + page["headings"]
                      + page["paragraphs"])
    sector = detect_sector(corpus)
    if sector:
        items.append({"label": "VERIFIED FACT",
                      "text": f"Sector signals on the homepage point to: {sector} "
                              "(keyword match on the site's own text).",
                      "source": src})
    for a in SECTOR_ASSUMPTIONS.get(sector, SECTOR_ASSUMPTIONS["default"]):
        items.append({"label": "ASSUMPTION", "text": a,
                      "source": "Signal Stack inference - not verified"})
    return items, sector, page["feeds"], None
