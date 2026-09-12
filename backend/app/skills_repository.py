"""
Loads the (skill_id, name) list from the SQL `skills` table so resume text
can be matched against known skills.

Expects a DATABASE_URL env var with a standard Postgres connection string
(Supabase gives you this in Project Settings > Database > Connection string).
Example:
    DATABASE_URL=postgresql://postgres:<password>@db.xxxx.supabase.co:5432/postgres

Falls back to a small static list if DATABASE_URL isn't set or the query
fails, so resume upload testing isn't blocked while waiting on Jason's
table to be seeded.
"""

import os
import time
from typing import List, Tuple

import psycopg2
from dotenv import load_dotenv

load_dotenv()

_DATABASE_URL = os.getenv("DATABASE_URL")

# Used only if the real skills table isn't reachable yet.
# Used only if the real skills table isn't reachable yet.
_FALLBACK_SKILLS: List[Tuple[int, str]] = [
    # --- Software Engineering / IT ---
    (1, "Python"),
    (2, "SQL"),
    (3, "JavaScript"),
    (4, "MongoDB"),
    (5, "Docker"),
    (6, "Machine Learning"),
    (7, "Excel"),
    (8, "Power BI"),
    (9, "Java"),
    (10, "C++"),
    (11, "C#"),
    (12, "Git"),
    (13, "Linux"),
    (14, "REST APIs"),
    (15, "Agile / Scrum"),
    (16, "SDLC"),
    (17, "Object-Oriented Programming"),
    (18, "Data Structures & Algorithms"),
    (19, "PostgreSQL"),
    (20, "MySQL"),
    (21, "Kubernetes"),
    (22, "CI/CD"),
    (23, "AWS"),
    (24, "Azure"),
    (25, "Troubleshooting"),

    # --- Web Development ---
    (26, "HTML/CSS"),
    (27, "React.js"),
    (28, "Node.js"),
    (29, "TypeScript"),
    (30, "Vue.js"),
    (31, "Angular"),
    (32, "Express.js"),
    (33, "Next.js"),
    (34, "Tailwind CSS"),
    (35, "WordPress"),
    (36, "Responsive Design"),
    (37, "Front-End Development"),
    (38, "Back-End Development"),
    (39, "Full-Stack Development"),

    # --- Data Science & Analytics ---
    (40, "R"),
    (41, "Pandas"),
    (42, "NumPy"),
    (43, "TensorFlow"),
    (44, "PyTorch"),
    (45, "Data Visualization"),
    (46, "Statistical Analysis"),
    (47, "Deep Learning"),
    (48, "Natural Language Processing"),
    (49, "Tableau"),
    (50, "Data Cleaning"),
    (51, "A/B Testing"),
    (52, "Predictive Modeling"),

    # --- Cybersecurity ---
    (53, "Network Security"),
    (54, "Penetration Testing"),
    (55, "Vulnerability Assessment"),
    (56, "SIEM"),
    (57, "Incident Response"),
    (58, "Compliance"),
    (59, "Risk Management"),
    (60, "Cryptography"),
    (61, "Firewall Administration"),

    # --- Cloud & DevOps ---
    (62, "Terraform"),
    (63, "Jenkins"),
    (64, "Ansible"),
    (65, "GCP"),
    (66, "Shell Scripting"),
    (67, "Bash"),
    (68, "Microservices"),
    (69, "Containerization"),
    (70, "Monitoring & Logging"),

    # --- Marketing & Digital ---
    (71, "SEO/SEM"),
    (72, "Google Analytics"),
    (73, "Social Media Marketing"),
    (74, "Content Strategy"),
    (75, "Email Marketing"),
    (76, "Copywriting"),
    (77, "Brand Management"),
    (78, "Market Research"),
    (79, "CRM"),
    (80, "HubSpot"),
    (81, "Canva"),
    (82, "Hootsuite"),

    # --- Finance & Accounting ---
    (83, "Financial Analysis"),
    (84, "Bookkeeping"),
    (85, "QuickBooks"),
    (86, "SAP"),
    (87, "Financial Modeling"),
    (88, "Budgeting"),
    (89, "Forecasting"),
    (90, "Tax Preparation"),
    (91, "Auditing"),
    (92, "VLOOKUP / Pivot Tables"),

    # --- Project Management ---
    (93, "Jira"),
    (94, "Confluence"),
    (95, "MS Project"),
    (96, "Stakeholder Management"),
    (97, "Risk Management"),
    (98, "Resource Planning"),
    (99, "Waterfall Methodology"),
    (100, "Kanban"),
    (101, "Scrum Master"),

    # --- HR & Administration ---
    (102, "Recruiting"),
    (103, "Onboarding"),
    (104, "Employee Relations"),
    (105, "Payroll"),
    (106, "Performance Management"),
    (107, "HRIS"),
    (108, "Calendar Management"),
    (109, "Meeting Coordination"),
    (110, "Travel Arrangements"),

    # --- Design & Creative ---
    (111, "Figma"),
    (112, "Adobe Photoshop"),
    (113, "Adobe Illustrator"),
    (114, "Adobe XD"),
    (115, "Sketch"),
    (116, "UI/UX Design"),
    (117, "Prototyping"),
    (118, "Wireframing"),
    (119, "Graphic Design"),
    (120, "User Research"),

    # --- Sales & Business ---
    (121, "Lead Generation"),
    (122, "Negotiation"),
    (123, "Client Relationship Management"),
    (124, "Cold Calling"),
    (125, "Salesforce"),
    (126, "B2B Sales"),
    (127, "Business Development"),
    (128, "Proposal Writing"),
    (129, "Pipeline Management"),

    # --- Soft Skills (universal) ---
    (130, "Communication"),
    (131, "Team Collaboration"),
    (132, "Problem-Solving"),
    (133, "Critical Thinking"),
    (134, "Time Management"),
    (135, "Adaptability"),
    (136, "Leadership"),
    (137, "Attention to Detail"),
    (138, "Organizational Skills"),
    (139, "Technical Documentation"),
    (140, "Cross-Functional Collaboration"),
]

_CACHE_TTL_SECONDS = 300  # re-fetch from SQL at most every 5 minutes
_cache: List[Tuple[int, str]] = []
_cache_loaded_at: float = 0.0


def _fetch_skills_from_sql() -> List[Tuple[int, str]]:
    """Query skill_id, name from the SQL skills table."""
    if not _DATABASE_URL:
        raise RuntimeError("DATABASE_URL not set")

    conn = psycopg2.connect(_DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT skill_id, name FROM skills;")
            return cur.fetchall()
    finally:
        conn.close()


def get_all_skills(force_refresh: bool = False) -> List[Tuple[int, str]]:
    """
    Returns a list of (skill_id, name) tuples, cached in memory.
    Falls back to a static list if the SQL table isn't reachable.
    """
    global _cache, _cache_loaded_at

    is_stale = (time.time() - _cache_loaded_at) > _CACHE_TTL_SECONDS
    if force_refresh or is_stale or not _cache:
        try:
            _cache = _fetch_skills_from_sql()
            _cache_loaded_at = time.time()
        except Exception as exc:
            if not _cache:
                # No usable cache yet - use the fallback so callers aren't blocked.
                print(f"[skills_repository] Falling back to static skills list: {exc}")
                _cache = _FALLBACK_SKILLS
                _cache_loaded_at = time.time()
            # If we already have a cache from a previous successful fetch,
            # keep using it rather than overwriting with the fallback.

    return _cache