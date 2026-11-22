# FirstStep

**Coordinate childcare, transport, and bridge funding so a first day at work can happen.**

FirstStep is a runnable hackathon prototype with a constrained planning engine, a public-data explorer, a paired Monte Carlo simulator, and a locally trained predictive model. All applicant cases, service offers, confirmations, and outcomes in the coordination studio and simulator are **synthetic**. The research explorer uses real public-source records.

![FirstStep coordination studio](docs/preview.png)

## Run in one command

Python 3.11 or newer. No runtime packages, API keys, or cloud accounts required.

```sh
python -m firststep.server
```

Open **http://127.0.0.1:8080**. Use `--port 8090` to select another port. Run commands from the repository root.

Demo state persists between runs. To repeat the demo from a clean start, run `python -m firststep.server --reset-demo`, which clears saved plans, events, simulation reports, and the learned policy. A locally retrained model is kept. For a `firststep` command, install from the checkout with `pip install -e .`.

## The three-minute demo

1. In **Coordination studio**, keep the synthetic applicant's defaults and select **Find a coordinated plan**. The planner checks six childcare/transport combinations and selects the lowest-cost feasible bundle: $260 per week.
2. Check the simulation-consent box and confirm the demo arrangement.
3. Record a **15-minute transport delay**. No external service is contacted.
4. In **Learning lab**, evaluate the proposed scheduling change. The five-case stress suite favors a 15-minute buffer, but a broader 500-household paired check exposes lost access. The gate retains the current policy when the candidate reduces total on-time starts, increases late arrivals, or declines more of the five stress scenarios. When several delays were observed, it tests the largest one that can pass, so one extreme delay cannot block a safe improvement.
5. Open **Simulator & model** and compare 0-minute and 15-minute buffers across hundreds of households. Inspect late arrivals, declined plans, costs, paired changes, and the actual trained model's conditional probabilities.
6. Create and confirm another studio plan, then **simulate a provider withdrawal**. The engine excludes the withdrawn offer, checks a replacement, and requires fresh consent. If no valid replacement fits the budget, it reports the blockers.

These are synthetic results, not measured employment or social-impact outcomes. The scheduling learner proposes one bounded parameter and cannot rewrite provider rules or its tests. Predictive-model training is a separate, explicit local operation. Existing saved demo policies are preserved; the broader gate applies to new proposals.

## What is implemented

- Budget, deposit, age, drop-off, arrival, pickup, and withdrawn-offer constraints.
- Enumeration and transparent rejection reasons for all six combinations.
- Explicit consent, idempotent demo confirmation, persisted outcomes, and an audit trail.
- Provider-withdrawal replanning with renewed consent.
- Observed-delay evidence, candidate-policy evaluation, and gated promotion.
- Real county statistics and a historical California childcare-center directory.
- Optional full SQLite research database with tract and block-group search.
- Reproducible paired simulation with configurable transport delays, provider withdrawals, and funding failures.
- Locally trained logistic regression, held-out evaluation, calibration bins, inspectable coefficients, and saved weights.
- Responsive, keyboard-accessible web interface with a self-hosted font and no external font or script requests.
- Research search that ignores extra spaces and accents, so `Anasco` finds Añasco Municipio.

## Real data included

The repository includes a small usable extract so a fresh clone works immediately:

| File | Contents |
| --- | --- |
| `data/county_profiles.csv` | 3,222 county/county-equivalent profiles from the 2020–2024 ACS |
| `data/ca_childcare_centers.csv` | 19,426 historical California center records across licensing statuses; the UI filters source-listed LICENSED records |
| `data/data_dictionary.csv` | Census labels and original variable names |
| `data/manifest.json` | Full database source URLs, checksums, row counts, and validation results |

Provider records are dated **May 25, 2025**. They are not a live directory. Licensed capacity is not a vacancy count. Census negative sentinel values are retained in source data and displayed as unavailable; published margins of error are shown where selected. Geographic levels overlap and must not be added together. Parental-employment fields count **children**, not parents.

The full database contains **1,499,965 source rows** across subject tables, including data for **330,954 unique geographic areas**, **48,308 historical childcare-price records**, and **39,184 California licensing records**. Repeated geographies across subject tables are not unique people. Provider records are not linked to Census geographies by guessed matches.

### Install the full database

The 304 MB SQLite database is distributed as a ~75 MB release asset rather than committed to Git history. Download the public research release with `gh`:

```sh
gh release download research-v1 --repo am101596-sketch/jestergooning --pattern FirstStep_Database.zip --dir data
python scripts/install_database.py data/FirstStep_Database.zip
python -m firststep.server
```

The installer verifies the archive's SHA-256, SQLite integrity, and expected geography count. An existing database is replaced only after validation. Alternatively, point `FIRSTSTEP_RESEARCH_DB` to an existing full database. The explorer opens it read-only. Price and family-home tables are available through SQL; the web interface currently exposes area profiles and center search.

## Research basis and unresolved assumptions

Childcare barriers are documented. A [St. Louis Fed analysis of 2024 survey data](https://www.stlouisfed.org/on-the-economy/2025/may/economics-child-care-state-level-analysis) reports that 16% of mothers with children under six who wanted work were not actively searching because they could not arrange childcare. This is not 16% of all mothers.

That evidence does not quantify the portion caused by sequencing failures, prove willingness to pay, or validate conditional reservations. Existing platforms such as [Unite Us](https://uniteus.com/products/closed-loop-referral-system/) already provide social-service coordination. FirstStep's coordinated-commitment mechanism is a product hypothesis, not a claim of worldwide novelty. [SFUSD's rules](https://www.sfusd.edu/sfusds-early-education-department-handbook/section-20-enrollment-costs-fees/22-sfusds-early-education-application) include parents seeking employment, so having a job is not a universal prerequisite for childcare assistance.

A real pilot needs participating providers with verified rules, availability, reservation authority, and funding. Start with a workforce partner and review failed starts to distinguish coordination delays from unavailable capacity or money. Evaluate on-time starts, staff effort, failed arrangements, and subsequent employment retention against a suitable comparison.

## Architecture

```text
Browser: static HTML / CSS / JavaScript
    -> localhost HTTP API (Python standard library)
        -> pure constraint planner and fixed stress evaluator
        -> seeded Monte Carlo world and local logistic regression
        -> local SQLite demo-state store
        -> read-only research SQLite or bundled CSV fallback
```

Demo state persists in `data/state.sqlite`, which Git ignores. The server binds only to loopback, validates loopback Host headers, rejects cross-origin mutations, limits JSON payloads, and applies a restrictive content security policy. It has no production authentication or authorization model. Do not expose it on a public network or enter real applicant information. There are no live booking, payment, benefit-submission, or messaging integrations.

## Simulator and local predictive model

Open **Simulator & model** in the app. Set the number of households (10–5,000), seed, delay probability and mean, provider withdrawal and funding-failure probabilities, and two arrival-buffer policies. Both policies face the **same households and underlying random disturbances**. Outcomes include on-time, late, withdrawal, funding failure, and no feasible plan. Planned costs, paired changes, and an approximate Monte Carlo interval are reported separately. Running a simulation does not promote a policy or change active case records.

You can also run it without the web server:

```sh
python -m firststep.simulator --cases 1000 --seed 42 --output data/simulation.json
```

The checked-in `docs/simulation-example.json` records that run. Under its chosen assumptions, the 15-minute buffer reduces late arrivals from 77 to 30, but on-time starts fall from 471 to 371 because declines increase from 354 to 524. This is a synthetic illustration of a coverage/reliability tradeoff, not a claim about real services.

The generator assumes fixed demo offers, no inter-household capacity competition, independent provider/funding failures, exponential transport delays, and no recovery within a run. Those assumptions are controllable modeling choices, not measurements of real services. Provider withdrawal draws are provider-specific and shared across the two policies.

### Train entirely on your machine

```sh
python -m firststep.predictive --train 4000 --test 1000 --seed 20261122
```

Or select **Retrain locally** in the app. The pure-Python trainer uses batch gradient descent with L2 regularization. No external packages, downloaded language model, cloud inference, or GPU is needed. It saves the model to ignored `data/model.json`; a fresh clone uses the bundled, actually trained checkpoint at `models/readiness-v1.json`.

Training labels are generated outcomes for feasible synthetic plans. Features are pre-outcome arrival slack and supplied disruption assumptions. Normalization uses training rows only. Training and test cases use disjoint seed-based identifiers; the test set is never used to update weights or choose a threshold. Evaluation remains inside the same generator and is **not external validation**. Declined plans are not scored. Inputs outside the documented training ranges receive no prediction.

The bundled model was trained on **4,000 feasible plans** and tested on **1,000 separately generated plans**. Initial held-out results: **Brier loss 0.2076** versus **0.2275** for a constant training-prevalence baseline; **AUROC 0.6725**; accuracy **68.2%** versus **65.1%** for the constant baseline. These numbers describe the simulator, not real families. The UI displays calibration-bin counts so tiny samples are visible.

**Score studio applicant** estimates an on-time first attempt using the current studio policy and the simulator's risk settings. It does not select beneficiaries, override planner constraints, or claim calibrated real-world probabilities. Predictive retraining is separate from the Learning lab's existing gated scheduling-policy update.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests cover planner constraints, impossible cases, withdrawal recovery, consent and idempotency, persistence, policy gates, real-data fallback, and HTTP request handling. GitHub Actions runs the suite on Python 3.11–3.13.

## Data provenance and licensing

- **U.S. Census Bureau:** [2020–2024 ACS five-year Detailed Tables](https://www.census.gov/programs-surveys/acs/data/summary-file.2024.html), B01003, B19013, B23025, B23008, and B08201. Keep the period, geographic level, and uncertainty attached to estimates.
- **U.S. Department of Labor Women's Bureau:** [National Database of Childcare Prices](https://www.dol.gov/agencies/wb/topics/featured-childcare), 2008–2022. [Technical report](https://www.dol.gov/sites/dolgov/files/WB/National-Database-of-Childcare-Prices-Technical-Report.pdf) explains units, missingness, and estimation.
- **California Department of Social Services:** [Community Care Licensing Facilities](https://publish.data.ca.gov/dataset/community-care-licensing-facilities). The catalog identifies Creative Commons Attribution licensing. The bundled center CSV retains original source fields. UI filtering, SQLite conversion, and derived research views are project modifications. No government endorsement is implied.

- **Public Sans:** the interface typeface is self-hosted from `@fontsource-variable/public-sans` under the SIL Open Font License. See `static/public-sans-LICENSE.txt`.

Application code is MIT licensed. Source datasets and the font retain their own terms and attribution requirements; the application license does not replace them.
