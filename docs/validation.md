# Validation

The initial implementation was checked locally on Windows with Python 3.12 and headless Google Chrome.

- 16 Python tests passed, covering planner feasibility, impossible budgets, deposit and pickup constraints, provider withdrawal, malformed inputs, consent, repeated confirmation, persisted policy changes, CSV fallback, and HTTP behavior.
- JavaScript syntax check passed with Node.js.
- Browser flows passed: planning, missing-consent rejection, confirmation, withdrawal and replacement, transport-delay recording, policy promotion, changed connection selection, session restoration, county search, full-database block-group search, provider search, infeasible-budget explanation, and source disclosures.
- Browser checks reported no JavaScript exceptions. The 390 px mobile viewport had no document-level horizontal overflow. Desktop and mobile screenshots are included in this directory.

The initial fixed stress-suite result was 1 on-time / 2 late / 2 declined for the zero-buffer policy, and 3 on-time / 0 late / 2 declined for the 15-minute candidate. These five synthetic cases demonstrate the bounded update mechanism. They do not establish effectiveness for real families or generalization to unseen operational conditions.

CI is configured for Python 3.11–3.13. Local browser verification is separate from the Python CI suite.

## Simulator and predictive-model extension

The expanded Python suite has 28 tests, including reproducible random seeds, identical shocks for identical policies, outcome totals, zero/total disruption cases, refusal of unbounded inputs, disjoint synthetic splits, known probability metrics, learned performance against a constant baseline, saved-model inference, out-of-domain refusal, local retraining through HTTP, and the broader policy gate.

The model checkpoint was actually trained locally on 4,000 feasible synthetic plans. On 1,000 separately generated test cases, Brier loss was 0.207602 versus 0.227488 for a constant training-prevalence baseline; AUROC was 0.672499. Neither checkpoint selection nor gradient updates use test labels. This is same-generator evaluation and does not establish real-world validity.

Browser checks covered paired simulation, local retraining, probability scoring, refusal outside training ranges, persisted simulation reports, and mobile layout without JavaScript exceptions or document-level horizontal overflow.

The larger generator exposed a failure of the original five-case evaluation: a stricter buffer could lower late arrivals while reducing total on-time starts by declining more households. The Learning lab now adds a fixed 500-household paired check before adopting a proposal. It rejects that broader harm even when the five-case suite passes. The stored 1,000-case example is a demonstration report, separate from the fixed adoption check, and is not a real-world impact study.

## Interface and hardening pass

Each fix below was reproduced first, then checked again in headless Chrome against the full research database.

- The skip link no longer switches pages, and the missing-consent error stays visible where the person is working.
- A slow search can no longer overwrite a newer one. Missing income shows as "Unavailable" instead of "$Unavailable" (De Baca County, New Mexico).
- Text below WCAG AA contrast went from 93 elements across four screens to 0 across all five. This automated check covers rendered text in the default state of each screen. No screen-reader testing was done.
- No document-level horizontal overflow at 320, 390, 768, or 1024 px.
- The learning gate no longer adopts a buffer that declines more stress scenarios, and one extreme delay no longer blocks a safe buffer.
- Search treats `%` and `_` literally and ignores extra spaces and accents. Repeat searches of the bundled provider file dropped from about 159 ms to about 1 ms, at a cost of about 21 MB of memory after the first search.
