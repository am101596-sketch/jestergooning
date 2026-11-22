# Validation

The initial implementation was checked locally on Windows with Python 3.12 and headless Google Chrome.

- 16 Python tests passed, covering planner feasibility, impossible budgets, deposit and pickup constraints, provider withdrawal, malformed inputs, consent, repeated confirmation, persisted policy changes, CSV fallback, and HTTP behavior.
- JavaScript syntax check passed with Node.js.
- Browser flows passed: planning, missing-consent rejection, confirmation, withdrawal and replacement, transport-delay recording, policy promotion, changed connection selection, session restoration, county search, full-database block-group search, provider search, infeasible-budget explanation, and source disclosures.
- Browser checks reported no JavaScript exceptions. The 390 px mobile viewport had no document-level horizontal overflow. Desktop and mobile screenshots are included in this directory.

The initial fixed stress-suite result was 1 on-time / 2 late / 2 declined for the zero-buffer policy, and 3 on-time / 0 late / 2 declined for the 15-minute candidate. These five synthetic cases demonstrate the bounded update mechanism. They do not establish effectiveness for real families or generalization to unseen operational conditions.

CI is configured for Python 3.11–3.13. Local browser verification is separate from the Python CI suite.
