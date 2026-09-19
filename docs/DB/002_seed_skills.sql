-- Jobless Simulator: synthetic development skill dictionary.
-- Change script 002; apply after 001_initial_schema.sql.
--
-- Purpose
--   The first milestone lets a student add confirmed skills by selecting an
--   existing dictionary entry (docs/API.md, GET /api/skills). There is no public
--   endpoint for creating canonical skills, so the dictionary has to be seeded
--   before the skill search, the resume matcher or the skill editor can be
--   exercised against real data.
--
-- Repeatability
--   Safe to run more than once. `skills_name_unique` in 001 is a unique index on
--   lower(name), so a name that already exists is skipped rather than duplicated.
--   Nothing is updated or deleted: rows a teammate added by hand are left alone.
--
-- Identifiers
--   skill_id is GENERATED ALWAYS AS IDENTITY. This script never supplies one and
--   the values it produces are not stable across databases. Application code and
--   fixtures must resolve a skill by canonical name:
--
--       SELECT skill_id FROM public.skills WHERE lower(name) = lower($1);
--
--   The IDs used as examples in docs/API.md are illustrative, not live values.
--   Re-running this script consumes identity values for the rows it skips, so
--   skill_id gaps after a second run are expected and harmless.
--
-- Contents
--   Synthetic development data, not a researched taxonomy. The names are taken
--   from the fallback list in backend/app/skills_repository.py so that existing
--   keyword matching keeps working once that fallback is removed. Synonyms
--   (Postgres/PostgreSQL, JS/JavaScript) are still normalized in application
--   code, not here. Refining this list is a team decision; add or remove entries
--   in a later numbered script rather than editing this one after it is applied.

BEGIN;

INSERT INTO public.skills (name) VALUES
    -- Software Engineering / IT
    ('Python'),
    ('SQL'),
    ('JavaScript'),
    ('MongoDB'),
    ('Docker'),
    ('Machine Learning'),
    ('Excel'),
    ('Power BI'),
    ('Java'),
    ('C++'),
    ('C#'),
    ('Git'),
    ('Linux'),
    ('REST APIs'),
    ('Agile / Scrum'),
    ('SDLC'),
    ('Object-Oriented Programming'),
    ('Data Structures & Algorithms'),
    ('PostgreSQL'),
    ('MySQL'),
    ('Kubernetes'),
    ('CI/CD'),
    ('AWS'),
    ('Azure'),
    ('Troubleshooting'),
    -- Web Development
    ('HTML/CSS'),
    ('React.js'),
    ('Node.js'),
    ('TypeScript'),
    ('Vue.js'),
    ('Angular'),
    ('Express.js'),
    ('Next.js'),
    ('Tailwind CSS'),
    ('WordPress'),
    ('Responsive Design'),
    ('Front-End Development'),
    ('Back-End Development'),
    ('Full-Stack Development'),
    -- Data Science & Analytics
    ('R'),
    ('Pandas'),
    ('NumPy'),
    ('TensorFlow'),
    ('PyTorch'),
    ('Data Visualization'),
    ('Statistical Analysis'),
    ('Deep Learning'),
    ('Natural Language Processing'),
    ('Tableau'),
    ('Data Cleaning'),
    ('A/B Testing'),
    ('Predictive Modeling'),
    -- Cybersecurity
    ('Network Security'),
    ('Penetration Testing'),
    ('Vulnerability Assessment'),
    ('SIEM'),
    ('Incident Response'),
    ('Compliance'),
    ('Risk Management'),
    ('Cryptography'),
    ('Firewall Administration'),
    -- Cloud & DevOps
    ('Terraform'),
    ('Jenkins'),
    ('Ansible'),
    ('GCP'),
    ('Shell Scripting'),
    ('Bash'),
    ('Microservices'),
    ('Containerization'),
    ('Monitoring & Logging'),
    -- Marketing & Digital
    ('SEO/SEM'),
    ('Google Analytics'),
    ('Social Media Marketing'),
    ('Content Strategy'),
    ('Email Marketing'),
    ('Copywriting'),
    ('Brand Management'),
    ('Market Research'),
    ('CRM'),
    ('HubSpot'),
    ('Canva'),
    ('Hootsuite'),
    -- Finance & Accounting
    ('Financial Analysis'),
    ('Bookkeeping'),
    ('QuickBooks'),
    ('SAP'),
    ('Financial Modeling'),
    ('Budgeting'),
    ('Forecasting'),
    ('Tax Preparation'),
    ('Auditing'),
    ('VLOOKUP / Pivot Tables'),
    -- Project Management
    ('Jira'),
    ('Confluence'),
    ('MS Project'),
    ('Stakeholder Management'),
    ('Resource Planning'),
    ('Waterfall Methodology'),
    ('Kanban'),
    ('Scrum Master'),
    -- HR & Administration
    ('Recruiting'),
    ('Onboarding'),
    ('Employee Relations'),
    ('Payroll'),
    ('Performance Management'),
    ('HRIS'),
    ('Calendar Management'),
    ('Meeting Coordination'),
    ('Travel Arrangements'),
    -- Design & Creative
    ('Figma'),
    ('Adobe Photoshop'),
    ('Adobe Illustrator'),
    ('Adobe XD'),
    ('Sketch'),
    ('UI/UX Design'),
    ('Prototyping'),
    ('Wireframing'),
    ('Graphic Design'),
    ('User Research'),
    -- Sales & Business
    ('Lead Generation'),
    ('Negotiation'),
    ('Client Relationship Management'),
    ('Cold Calling'),
    ('Salesforce'),
    ('B2B Sales'),
    ('Business Development'),
    ('Proposal Writing'),
    ('Pipeline Management'),
    -- Soft Skills (universal)
    ('Communication'),
    ('Team Collaboration'),
    ('Problem-Solving'),
    ('Critical Thinking'),
    ('Time Management'),
    ('Adaptability'),
    ('Leadership'),
    ('Attention to Detail'),
    ('Organizational Skills'),
    ('Technical Documentation'),
    ('Cross-Functional Collaboration')
ON CONFLICT (lower(name)) DO NOTHING;

COMMIT;

-- Verification. Run after the transaction commits.
--   Expect the dictionary size below, and skill_id values assigned by Postgres
--   rather than the numbers in this file's source list.
SELECT count(*) AS skills_in_dictionary FROM public.skills;
SELECT skill_id, name FROM public.skills ORDER BY lower(name), skill_id LIMIT 10;
