"""
Keyword/rule-based classification of a job posting into a profession
category and an industry category. Same approach as skill matching:
score each category by how many of its keywords appear in the text
(whole-word/phrase, case-insensitive), pick the highest score.

This is a heuristic, not a guarantee - ambiguous postings (e.g. a
"Data Analyst, Energy Trading" role) may get classified by whichever
category happens to have more keyword hits in the text. Expand the
keyword lists below as you find real postings that get misclassified.
"""

import re
from typing import Dict, List, Tuple

UNCLASSIFIED = "Unclassified"

PROFESSION_KEYWORDS: Dict[str, List[str]] = {
    "Software Engineering": [
        "software engineer", "software developer", "backend", "frontend",
        "full stack", "full-stack", "web developer", "programmer",
        "mobile developer", "ios developer", "android developer",
    ],
    "Data Science / Analytics": [
        "data scientist", "data analyst", "data engineer", "machine learning",
        "business intelligence", "data science", "analytics", "quantitative research",
        "quantitative analyst",
    ],
    "IT Support / Operations": [
        "it support", "helpdesk", "help desk", "system administrator",
        "network administrator", "technical support", "it technician",
        "desktop support", "it operations",
    ],
    "Cybersecurity": [
        "cybersecurity", "cyber security", "security analyst", "penetration tester",
        "information security", "soc analyst", "security engineer",
    ],
    "DevOps / Cloud": [
        "devops", "site reliability", "cloud engineer", "platform engineer",
        "infrastructure engineer", "kubernetes", "ci/cd engineer",
    ],
    "Product Management": [
        "product manager", "product owner", "product management",
    ],
    "Design": [
        "ux designer", "ui designer", "product designer", "graphic designer",
        "user experience", "user interface design",
    ],
    "Finance / Trading": [
        "trading", "trader", "quantitative finance", "risk management",
        "investment banking", "portfolio management", "financial analyst",
        "energy trading", "power trading",
    ],
    "Marketing": [
        "marketing", "seo", "content marketing", "digital marketing",
        "growth marketing", "brand manager",
    ],
    "Sales": [
        "sales representative", "account executive", "business development",
        "sales manager",
    ],
    "Human Resources": [
        "human resources", "hr generalist", "recruiter", "talent acquisition",
        "people operations",
    ],
}

INDUSTRY_KEYWORDS: Dict[str, List[str]] = {
    "Technology": [
        "saas", "tech startup", "software company", "platform", "app",
    ],
    "Finance / Banking": [
        "bank", "banking", "asset management", "hedge fund", "investment firm",
        "financial services",
    ],
    "Energy / Trading": [
        "energy market", "renewables", "power trading", "commodities",
        "natural gas", "energy transition", "ppa",
    ],
    "Healthcare": [
        "healthcare", "hospital", "clinical", "patient", "medical",
    ],
    "Retail / E-commerce": [
        "retail", "e-commerce", "ecommerce", "online store", "marketplace",
    ],
    "Education": [
        "university", "school", "education", "academic", "student",
    ],
    "Government / Public Sector": [
        "government", "public sector", "federal", "ministry",
    ],
}


def _score_categories(text: str, keyword_map: Dict[str, List[str]]) -> List[Tuple[str, int]]:
    """Returns (category, score) pairs, sorted highest score first."""
    text_lower = text.lower()
    scores = []

    for category, keywords in keyword_map.items():
        score = 0
        for keyword in keywords:
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", re.IGNORECASE)
            if pattern.search(text_lower):
                score += 1
        scores.append((category, score))

    scores.sort(key=lambda pair: pair[1], reverse=True)
    return scores


def classify_profession(text: str) -> str:
    """Returns the best-matching profession category, or 'Unclassified' if no keywords match."""
    scores = _score_categories(text, PROFESSION_KEYWORDS)
    top_category, top_score = scores[0]
    return top_category if top_score > 0 else UNCLASSIFIED


def classify_industry(text: str) -> str:
    """Returns the best-matching industry category, or 'Unclassified' if no keywords match."""
    scores = _score_categories(text, INDUSTRY_KEYWORDS)
    top_category, top_score = scores[0]
    return top_category if top_score > 0 else UNCLASSIFIED