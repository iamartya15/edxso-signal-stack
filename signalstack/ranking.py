"""Explainable signal ranking.

Every fetched signal gets an intelligence score from 1 to 100 built from
five transparent components (all 0-100):

    score = 0.30 * relevance     (match with the company's goals/products)
          + 0.25 * impact        (does the text describe a business event?)
          + 0.20 * authority     (how authoritative is the source?)
          + 0.15 * confidence    (how complete/verifiable is the item?)
          + 0.10 * freshness     (how recent is it?)

Priority bands: score >= 70 -> High, 40-69 -> Medium, below 40 -> Low.
Each signal also stores the matched evidence terms and a plain-language
reason, so a human can always see *why* it was ranked that way. No ML,
no black box: the same input always produces the same score.
"""
import re
from datetime import datetime, timezone

WEIGHTS = {"relevance": 0.30, "impact": 0.25, "authority": 0.20,
           "confidence": 0.15, "freshness": 0.10}

IMPACT_KEYWORDS = {
    "launch": 14, "launches": 14, "funding": 16, "raises": 14, "acquisition": 18,
    "acquires": 16, "merger": 18, "partnership": 12, "partners": 10,
    "regulation": 14, "policy": 10, "ban": 14, "lawsuit": 12, "fine": 10,
    "price": 8, "pricing": 10, "discount": 8, "offer": 6, "free": 5,
    "outage": 14, "recall": 16, "layoff": 14, "layoffs": 14, "hiring": 6,
    "expansion": 12, "expands": 12, "opens": 8, "shuts": 12, "bankrupt": 18,
    "ipo": 16, "valuation": 12, "growth": 8, "record": 8, "award": 8,
    "update": 5, "new": 4, "introduces": 12, "unveils": 12,
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "will", "your",
    "their", "about", "into", "over", "after", "before", "india", "indian",
    "company", "companies", "business", "services", "service", "solutions",
}


def terms_from(*texts):
    """Distinct meaningful keywords from profile text (goals/products/etc)."""
    words = set()
    for text in texts:
        if not text:
            continue
        for w in re.findall(r"[a-zA-Z]{3,}", text.lower()):
            if w not in STOPWORDS:
                words.add(w)
    return sorted(words)


def _clamp(v):
    return max(0, min(100, int(round(v))))


def score_signal(company_terms, category, title, description, authority,
                 published_dt, has_link=True):
    """Return the full ranking breakdown for one signal."""
    text = f"{title or ''} {description or ''}".lower()
    text_words = set(re.findall(r"[a-zA-Z]{3,}", text))

    # --- relevance: share of the company's own terms that appear ----------
    matched = [t for t in company_terms if t in text_words]
    if company_terms:
        relevance = _clamp(15 + 85 * (len(matched) / max(4, min(len(company_terms), 12))))
        if not matched:
            relevance = 10
    else:
        relevance = 30  # no goals recorded yet: neutral-low, stated openly

    # --- impact: weighted business-event keywords -------------------------
    hit_words = {k: v for k, v in IMPACT_KEYWORDS.items()
                 if re.search(rf"\b{re.escape(k)}\b", text)}
    impact = _clamp(sum(hit_words.values()))

    # --- confidence: completeness of the item -----------------------------
    confidence = 20
    if has_link:
        confidence += 25
    if published_dt is not None:
        confidence += 25
    if description and len(description) >= 120:
        confidence += 20
    elif description and len(description) >= 40:
        confidence += 10
    confidence = _clamp(confidence)

    # --- freshness: linear decay over 30 days -----------------------------
    if published_dt is None:
        freshness = 35  # undated item: cannot prove freshness
    else:
        if published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - published_dt).total_seconds() / 86400
        freshness = _clamp(100 - max(0.0, days) * 3.5)

    authority = _clamp(authority)
    total = (WEIGHTS["relevance"] * relevance + WEIGHTS["impact"] * impact
             + WEIGHTS["authority"] * authority
             + WEIGHTS["confidence"] * confidence
             + WEIGHTS["freshness"] * freshness)
    score = max(1, min(100, int(round(total))))

    priority = "High" if score >= 70 else ("Medium" if score >= 40 else "Low")

    evidence_bits = []
    if matched:
        evidence_bits.append("matches your terms: " + ", ".join(matched[:6]))
    if hit_words:
        evidence_bits.append("event words: " + ", ".join(list(hit_words)[:5]))
    if not evidence_bits:
        evidence_bits.append("no direct term or event match; kept for awareness")
    evidence = "; ".join(evidence_bits)

    impact_templates = {
        "Competitors": "Competitor movement can shift pricing, positioning and win rates in deals you contest.",
        "Customers": "Customer-side signal: reflects demand, satisfaction or friction among the people who pay you.",
        "Market": "Market signal: may change demand, regulation or budgets in the sector you sell into.",
        "Internal": "Internal/first-party signal: your own public footprint that customers and rivals can see.",
    }
    impact_text = impact_templates.get(category, impact_templates["Market"])
    if hit_words:
        impact_text += f" Trigger terms detected: {', '.join(list(hit_words)[:4])}."

    reason = (f"{priority} priority: score {score}/100 = relevance {relevance} "
              f"(30%), impact {impact} (25%), authority {authority} (20%), "
              f"confidence {confidence} (15%), freshness {freshness} (10%).")

    return {
        "relevance": relevance, "impact_component": impact,
        "authority": authority, "confidence": confidence,
        "freshness": freshness, "score": score, "priority": priority,
        "evidence": evidence, "impact_text": impact_text,
        "priority_reason": reason,
    }
