# Procurement Audit Planner (West Berkshire Council)

An agentic system that plans an internal audit of procurement for West Berkshire
Council from its **public** data. It turns the council's Contract Procedure Rules
into testable rules, analyses the whole spend population against them, folds in
past audit history, rates the risks, and produces a cross-checked audit planning
pack that a human auditor approves and signs off.

All outputs are **risk indicators to investigate**. They are not findings of
wrongdoing by the council, any department or any supplier.

## The problem it solves

Planning a procurement audit is slow, manual and mostly reading-based. Auditors
read a ~50-page rulebook and years of committee papers, then pick a small random
sample of payments before analysing the full data.

1. **Slow:** reading the rulebook and committee papers takes days.
2. **Random sampling misses risk:** 25 random payments out of thousands will almost
   certainly miss the handful worth looking at.
3. **Inconsistent:** two auditors produce different ratings from the same material.
4. **Patterns are invisible one at a time:** split purchases, threshold-hugging and
   spend with no published contract notice only appear when the whole population is
   analysed together.

Design principles (from `CLAUDE.md`):

- **The LLM reads and judges; Python computes every number.**
- **Everything is traceable:** verbatim quotes checkable against the PDF; every
  metric named and reproducible from a script; every rating cites a rule, a metric
  or a prior finding.
- **Indicators, not accusations.**
- **Context discipline:** agents inspect data through aggregates only; big lists go
  to files.
- **Missing or malformed input means stop and report.** Nothing is fabricated.

---

## 1. Skills I created

Each skill is a folder in `.claude/skills/` with a `SKILL.md` and a script that does
the numeric or verifying work, so the model only supplies judgments.

| Skill | Invoked by | What it does | Inputs | Outputs | Verifier / builder |
|---|---|---|---|---|---|
| `extract-rules` | Human, with `/extract-rules` | Converts the Contract Procedure Rules PDF into one JSON entry per testable rule (clause, page, thresholds as printed, required action, verbatim quote). Every other clause goes in `excluded` with a reason; contradictions and drafting gaps go in `notes`. Thresholds the PDF only names stay as parameters with a null value, never filled from memory. | `data/contract-rules.pdf` | `outputs/rules.json` | `verify_quotes.py` checks every quote exists on the stated page and that every clause is in `rules` or `excluded` |
| `risk-assessment` | Loaded by the `risk-assessor` sub-agent | Method for merging rules, analytics and history into a risk register. The agent writes cited judgments with `{{$.path}}` placeholders; it never types a figure or multiplies a score. | `rules.json`, `analytics.json`, `history.json`, and later the auditor's decisions | `outputs/risk-ratings.json` (judgments), then `risk-register.md` and `auditor-comments.md` (rendered) | `build_register.py` resolves citations, fills figures, computes score and band from the council's own method, and enforces the auditor gate. Tested by `test_build_register.py` |
| `audit-program` | Loaded by the `planner` teammate | Method for turning approved risks into controls, test steps, sample recipes and a PBC (request) list. The planner writes judgments only. | `risk-register.md`, `auditor-comments.md`, `risk-ratings.json`, analytics and rules | `outputs/audit-plan.json` (judgments), then `planning-memo.md`, `risk-control-matrix.md`, `audit-program.md`, `samples/T-*.csv`, `pack-figures.json` (rendered) | `build_pack.py` checks the gate, resolves citations, draws each sample, verifies every sampled transaction against the cleaned spend, and renders the pack. `--gate` runs only the gate check. Tested by `test_build_pack.py` |

## 2. Agents I created

All six are defined in `.claude/agents/` and use project memory
(`.claude/agent-memory/<agent>/`), which holds how-to lessons only, never evidence.

### Sub-agents (run one after another, report to the main session)

| Agent | Role | Tools | Inputs | Outputs |
|---|---|---|---|---|
| `spend-analyst` | Cleans the spend workbooks and contract notice export, then writes and runs Python to produce reproducible risk indicators. | Bash, Read, Write, Edit, Glob, Grep | `rules.json`, `data/spend/*.xlsx`, `data/contracts.csv` | `outputs/analytics.json`, `outputs/analytics-full/*.csv`, `scripts/*.py`, `scripts/self_check.py` |
| `findings-analyst` | Records what the committee papers say: audits and opinions, follow-ups, risk themes, and the council's scoring method. Records only; never rates. | Bash, Read, Write, Edit, Glob, Grep | `data/committee/*.pdf` | `outputs/history.json` (each item has source file, PDF page and a copy-exact quote); checked by `scripts/verify_history.py` |
| `risk-assessor` | Follows the `risk-assessment` skill to recommend risks, likelihood, impact and focus. Recommends only; the auditor decides scope. | Bash, Read, Write, Edit, Glob, Grep | `rules.json`, `analytics.json`, `history.json`, `auditor-comments.md` on a re-run | `outputs/risk-ratings.json`, then (via the builder) `risk-register.md`, `auditor-comments.md` |

### Agent-team teammates (run at the same time and message each other)

| Agent | Role | Tools | Inputs | Outputs |
|---|---|---|---|---|
| `planner` | Follows the `audit-program` skill. Plans only auditor-approved risks. Answers the challenger, fixes QA failures, rebuilds. | Bash, Read, Write, Edit, Glob, Grep, SendMessage | Register, decisions, ratings, analytics, rules | `outputs/audit-plan.json`; the builder then writes the three pack documents and samples |
| `challenger` | Looks for weak spots: a low rating against a strong data signal, a control that does not match its rule, a sample aimed at the wrong place, an untested rule. Sends at most 8 challenges, then at most 4 more. Challenges and records; never fixes. | Bash, Read, Write, Edit, Glob, Grep, SendMessage | Register, decisions, ratings, analytics, history, rules, the built pack | `outputs/challenges.md` |
| `qa-reviewer` | Runs the four check scripts on every pack version and reports exactly what they print. Fixes nothing and softens nothing. Writes the verdict and the auditor's sign-off block. | Bash, Read, Write, Edit, Glob, Grep, SendMessage | The pack, `challenges.md`, `scripts/checks/*.py` | `outputs/review.md` |

### Why sub-agents here and teammates there

- **Sub-agents** (steps 2 and 3) do self-contained jobs with a clear input and a
  file as output. They need no conversation with each other, and each can run in a
  fresh context so the large PDFs and spreadsheets never enter the main session.
  The main session launches them and relays their reports. The three can be
  separate because `spend-analyst` and `findings-analyst` do not depend on each
  other; `risk-assessor` only needs their files.
- **Teammates** (step 5) have work that is genuinely back-and-forth: the challenger
  questions the planner, the planner revises and re-announces, and QA re-checks each
  new version. That needs direct messaging between agents (`SendMessage`), which
  sub-agents do not have. Agent teams are enabled with
  `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json`.
  Separate agents also mean the checker is not the author: QA is independent of the
  planner.

---

## 3. How they work together

```
 data/contract-rules.pdf
        |
 (1) /extract-rules  [SKILL, run by the human]  --> verify_quotes.py
        |
   rules.json
        |
        +---------------------------+---------------------------+
        |                                                       |
 (2) spend-analyst [SUB-AGENT]                      findings-analyst [SUB-AGENT]
     spend xlsx + contracts.csv                          committee PDFs
     writes + runs scripts/*.py                          verify_history.py
        |                                                       |
   analytics.json + analytics-full/                       history.json
        +---------------------------+---------------------------+
                                    |
 (3) risk-assessor [SUB-AGENT] loads risk-assessment [SKILL]
     writes risk-ratings.json  -->  build_register.py
                                    |
              risk-register.md + auditor-comments.md
                                    |
 (4) HUMAN GATE 1: auditor APPROVE / REJECT / REVISE / OVERRIDE each risk
        |  (REVISE / OVERRIDE / REJECT: risk-assessor re-run, register v2)
        v
     build_pack.py --gate   (stops if any risk is undecided)
                                    |
 (5) AGENT TEAM (messages between teammates)
        planner  --audit-program SKILL--> audit-plan.json --build_pack.py--> pack v1
           ^   |                                                       |
           |   +--- "PACK READY vN" ---> challenger --> challenges.md  |
           +-------- responses / rebuild ---------+                    |
           +------ "QA vN: FAIL ..." <-- qa-reviewer <-- scripts/checks/*.py
                                    |
              PLANNER DONE + CHALLENGER DONE + QA DONE
                                    |
 (6) HUMAN GATE 2: auditor signs off review.md (valid only if READY FOR SIGN-OFF)
```

Flow in words:

1. The human runs `/extract-rules`. The skill produces `rules.json`, and
   `verify_quotes.py` confirms every quote.
2. `spend-analyst` and `findings-analyst` run independently. One produces
   `analytics.json` (computed by code); the other produces `history.json` (read
   from the papers, with quotes).
3. `risk-assessor` merges the three files into cited ratings. `build_register.py`
   computes scores and bands from the council's own scoring method and writes the
   register and the decision template.
4. **Human gate 1.** The auditor records a decision on every risk in
   `auditor-comments.md`. `build_register.py` will not build a revised register
   until every risk has a decision, and `build_pack.py --gate` will not let the
   team start otherwise.
5. The agent team plans only the approved risks. The challenger raises issues, the
   planner accepts or limits them, and QA re-runs the four checks on every
   version. QA blocks sign-off until all checks pass.
6. **Human gate 2.** The auditor completes the sign-off block in `review.md`.

---

## 4. Completion checklist (Procurement Audit Planner guide)

Guide: <https://procurement-audit-planner.vercel.app/>

The guide page lists each lesson with a step count but not individual step titles,
so each row below covers a range of steps and names the file that evidences it.
Setup has 7 steps in total: the two prerequisites plus 1.1 to 1.5. All 7 are done.

| Lesson | Steps | Done | Evidence from my run |
|---|---|---|---|
| Setup | Prerequisite 1: VS Code installed | Done | Completed by me |
| Setup | Prerequisite 2: Claude Code installed and signed in | Done | Completed by me; the agents and skills in this repo ran in Claude Code |
| Setup | 1.1-1.5 | Done | Project folder with `CLAUDE.md`; Python `.venv` and `requirements.txt`; public data in `data/` (rules PDF, 3 monthly spend workbooks, `contracts.csv`, 4 committee PDFs) |
| Lesson 1: Skills | 2.1-2.2 | Done | `extract-rules` skill built and run: **73 rules**, 45 excluded entries, 2 parameters, 23 notes from a 15-page PDF; `verify_quotes.py` passes |
| Lesson 2: Sub-agents | 3.1-3.7 | Done | `spend-analyst`, `findings-analyst` and `risk-assessor` built and run; see headline numbers below |
| Lesson 3: Human gate | 4.1-4.3 | Done | I decided all 8 risks in `auditor-comments.md`; the register was revised to v2 |
| Lesson 4: Agent teams | 5.1-5.8 | Done | Team of `planner`, `challenger`, `qa-reviewer` run from `.claude/agents/`; pack **v3**; QA passed; sign-off recorded in `review.md` |

### Key results from my run

**Rules (`rules.json`):** 73 testable rules, 45 excluded clauses, 23 notes
(drafting gaps and contradictions), 2 named parameters.

**Analytics (`analytics.json`), 3 months of spend, 1 May to 31 July 2026:**

| Measure | Result |
|---|---|
| Spend rows read / analysed / excluded | 10,607 / 8,530 / 2,077 (reconciles to the penny) |
| Distinct suppliers analysed | 1,083 |
| Contract notices kept (council buyer) | 141 of 150 rows read; 9 other buyers dropped |
| Threshold clustering (within 10% below a tier) | 294 items below 1,000; 45 below 25,000; 0 below 500,000 |
| Split-purchase groups (30-day window) | 272 at 1,000; 299 at 25,000; 12 at 500,000 |
| Possible duplicates (same supplier and amount, 7 days) | 651 items; 453 groups identical on every published field |
| Suppliers meeting the quote threshold (annualised estimate) | 672 |
| Off-contract indicator (no exact notice match) | 632 suppliers; 17 have a possible near-miss notice for the auditor to review |
| Expired-notice indicator | 8 suppliers |
| Spend-vs-award indicator (ratio 1.25 or more) | 7 flagged of 18 assessed |

**History (`history.json`):** 4 source papers, 16 audits, 3 follow-ups, 1 advisory
item, 3 risk themes, 4 audit-plan statements and 7 gaps. 96 items carry a
copy-exact quote. The council's scoring method is usable (5x5, with bands and
escalation), and 11 internal inconsistencies in it are recorded as discrepancies.

**Register and my decisions (v2):**

| Risk | Title | Rating | My decision |
|---|---|---|---|
| R-01 | Same-supplier payments combining past the quote threshold | 20 Extreme | APPROVE |
| R-04 | Spend with suppliers having no council contract notice | 20 Extreme | APPROVE |
| R-02 | Low-value payments clustering and combining at the lowest quote boundary | 15 Extreme | APPROVE |
| R-03 | Combined payments approaching the high-value approval and tender tier | 15 Extreme | APPROVE |
| R-06 | Spend running above the awarded contract value | 15 Extreme | APPROVE |
| R-05 | Payments after the only matching notice has ended | 12 Medium-High (Amber) | OVERRIDE: likelihood set to 4 |
| R-07 | Possible duplicate payments | 8 Medium-High (Amber) | APPROVE, keeping likelihood at 2 |
| R-08 | Care and education placement spend without a published notice | removed | REJECT (separate social care commissioning review) |

**Pack (v3):** 7 risks, 7 controls, 7 tests, 1,456 sampled transactions in 7 sample
files. The challenger raised 9 challenges and the planner accepted all 9; none were
marked for the auditor.

**QA (`review.md`, final run):** all four checks pass with 0 failures and 0 pending.

| Check | Items checked |
|---|---|
| Quotes | 91 |
| Numbers | 161 |
| Trace | 97 |
| Samples | 1,456 |

**Verdict:** READY FOR SIGN-OFF.

**Sign-off:** SIGNED OFF by Isabel on 2026-10-10, pack v3. Comment: accepted with the
noted limitations on Challenge #1, the R-07 rule link and the T-04 sample.

---

## 5. My data decisions and known limitations

### Decisions I confirmed (2026-10-10)

- **Buyer-name filter:** match the contracts export case-insensitively, after
  trimming spaces, against "West Berkshire Council" or "West Berkshire".
- **Identical spend rows:** the spend data has no transaction ID. Rows identical on
  every field are all kept and flagged as possible duplicates, never removed.
- **Contracts dates:** Published Date is parsed as ISO 8601; the other dates as D/M/Y.
  Spend dates are M/D/Y. All formats are explicit; none are auto-detected.
- **Contract date columns:** use `Contract start date` and `Contract end date`.
- **Disjoint tests:** `off_contract` and `expired_notice_spend` never list the same
  supplier. A supplier whose exact-matching notices all ended before the window is
  reported only under `expired_notice_spend`. Non-exact name matches are candidates
  for the auditor and never count as matches.
- **Six conflicts in the council's scoring method** (the register header states all
  six): impact Medium is 3 (Table 1); the printed £ bands are used, with exactly
  £500k at impact 4; only the five likelihood labels are used, not probability
  percentages; Table 4's band name is used, with the matrix label shown beside it;
  the Corporate Risk Register threshold is Table 4's Extreme (15-25); Table 4's
  escalation is used, not paragraph 6.3.
- **R-08 rejected:** care placements recur by design and will be covered by a separate
  review.
- **R-05 overridden** to likelihood 4, and **R-07 kept at likelihood 2** because no
  Contract Procedure Rule covers duplicates and identical rows may be export
  artefacts.

### Known limitations

- **Three months only.** The "annualised estimate" is the window total times four
  and is an estimate, not a forecast.
- **Spend dates are payment-run timestamps**, not invoice dates, so the 30-day and
  7-day windows are measured on payment-run dates.
- **Notice coverage:** Contracts Finder publishes contracts above about £25k, so the
  absence of a notice for a smaller supplier is expected. The off-contract test only
  flags suppliers above that threshold. The export had 150 rows, well under the
  1,000-row cap.
- **Name matching only.** The spend data has no Companies House number, so matching
  to notices is by normalised name. Candidates are never counted as matches.
- **Tags are a heuristic** on published fields (narrative, category, service). They
  are not a classification of the underlying contract.
- **Redacted suppliers** cannot be tested by supplier. They are excluded and reported
  by category and tag.
- **Public-body list and exclusion pairs** (101 names and 5 pairs) remain in the
  analysed population for the auditor to review.
- **Spend-vs-award coverage is partial:** many suppliers are skipped because they have
  several active notices or a multi-supplier notice; award values may be estimates or
  maxima.
- **Challenge #1 only partly met:** the builder filters whole groups, not rows, so
  care- and grant-tagged rows remain inside sampled groups. The memo marks them as
  context only.
- **R-07 rule link:** no rule addresses duplicate payments directly, so its control
  cites the rule on publishing spend over £500.
- **T-04 sample:** 16 of the 17 off-contract suppliers with a candidate notice are in
  the sample; the 17th is not.
- **Council's own method is internally inconsistent** in places (see the six conflicts
  above). The Strategic Risk Register is exempt and not public, so it was not used.
- **Public data only.** Nothing here has been checked with the council.

---

## 6. How to run it

Prerequisites: Python 3 with a virtual environment and Claude Code.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt     # pandas, openpyxl
```

Place the public data in `data/` (`contract-rules.pdf`, `spend/*.xlsx`,
`contracts.csv`, `committee/*.pdf`). Agent teams need
`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` in `.claude/settings.json` (already set).

In Claude Code, from the project root:

1. **Rules:** run `/extract-rules`. Verify with
   `.venv/bin/python .claude/skills/extract-rules/verify_quotes.py`.
2. **Analysis:** ask Claude to run the `spend-analyst` and the `findings-analyst`
   sub-agents. The analysis runs from `scripts/run.py`; the history check is
   `scripts/verify_history.py`.
3. **Register:** ask Claude to run the `risk-assessor` sub-agent. It builds
   `outputs/risk-register.md` and `outputs/auditor-comments.md`.
4. **Gate 1:** edit the Decision and Comment columns in `outputs/auditor-comments.md`
   (APPROVE, REJECT, REVISE or OVERRIDE for each risk), then re-run the
   `risk-assessor` to produce the revised register.
5. **Team:** ask Claude to run the agent team. The lead first runs
   `.venv/bin/python .claude/skills/audit-program/build_pack.py --gate`, then starts
   `planner`, `challenger` and `qa-reviewer` as teammates.
6. **Gate 2:** review `outputs/review.md` and complete the sign-off block.

Checks and tests can also be run by hand:

```bash
.venv/bin/python scripts/checks/run_checks.py --final
.venv/bin/python -m pytest .claude/skills/risk-assessment/test_build_register.py
.venv/bin/python -m pytest .claude/skills/audit-program/test_build_pack.py
```

(`pytest` is not in `requirements.txt`; install it first if you want to run the tests.)

---

## 7. Repository structure

```
procurement-audit-planner/
  README.md
  CLAUDE.md                        # full system description
  requirements.txt
  data/                            # public inputs, read-only
    contract-rules.pdf
    contracts.csv
    spend/*.xlsx                   # 3 monthly workbooks
    committee/*.pdf                # 4 Governance Committee papers
  .claude/
    settings.json                  # enables agent teams
    skills/
      extract-rules/               # SKILL.md, verify_quotes.py
      risk-assessment/             # SKILL.md, build_register.py, test_build_register.py
      audit-program/               # SKILL.md, build_pack.py, test_build_pack.py
    agents/
      spend-analyst.md             # sub-agent
      findings-analyst.md          # sub-agent
      risk-assessor.md             # sub-agent
      planner.md                   # team teammate
      challenger.md                # team teammate
      qa-reviewer.md               # team teammate
    agent-memory/                  # per-agent how-to lessons (never evidence)
  scripts/                         # Python written by spend-analyst
    run.py, clean.py, contracts.py, thresholds.py, tests.py, tagging.py,
    common.py, config.py, tag_map.json, self_check.py,
    build_history.py, verify_history.py, tests/
    checks/                        # run by qa-reviewer
      run_checks.py, check_quotes.py, check_numbers.py,
      check_trace.py, check_samples.py, test_checks.py
  outputs/
    rules.json
    analytics.json
    analytics-full/                # full flagged lists + cleaned_spend.csv
    history.json
    committee-text/                # text extracted from the committee PDFs
    risk-ratings.json              # risk-assessor judgments
    risk-register.md               # rendered by build_register.py
    auditor-comments.md            # my decisions
    audit-plan.json                # planner judgments
    planning-memo.md               # rendered by build_pack.py
    risk-control-matrix.md
    audit-program.md
    samples/T-01.csv ... T-07.csv  # sampled transactions per test
    pack-figures.json              # every figure the builder computed
    challenges.md                  # challenger record
    review.md                      # QA results, verdict and my sign-off
```

---

# Part B: the deployed agent harness

Part A (above) is the audit planner as Claude Code skills and agents. Part B wraps the
same files in a small web application so the whole workflow can be viewed, and the key
steps run live, from a browser with no local setup.

**What it is.** A FastAPI server that uses the Claude Agent SDK. Live jobs run in a
throwaway copy of this folder, with `CLAUDE.md`, `.claude/skills`, `.claude/agents` and
`scripts/` loaded through `setting_sources=["project"]`, so the agents on the server are
the same files that ran in Claude Code. One web page shows the six stages with live
status and renders every output.

## How to use the demo

1. **Browse (free, no login).** Open the site. You are looking at the *committed run*, the
   complete output of the original Claude Code run: rules (stage 1), analytics and audit
   history (2), the risk register (3), the auditor's decisions (4), the planning memo,
   risk-control matrix, audit program, challenges and QA review (5), and the signed
   `review.md` (6). Browsing never calls a model.
2. **Run live (access code needed).** The owner gives graders an access code; enter it in
   the box at the top right. Then:
   - **Stage 4 (the main demo).** Change at least one decision (for example, make R-02 an
     `OVERRIDE` with `likelihood=2`) and submit. The server writes `auditor-comments.md`,
     reruns the **risk-assessor** agent, streams its steps to the page, and shows the
     revised register in the **Live run** view (R-02 should drop from 15 to 6, with a
     "Revision v3" section naming the change).
   - **Stage 3.** "Rerun stage" rebuilds the register from scratch (the agent rates the
     risks again, so the result will differ from the committed register).
   - **Stage 6.** The sign-off form writes the sign-off block of `review.md` in the live
     copy. SIGNED OFF is refused if the QA verdict is not READY FOR SIGN-OFF or if a live
     change has made the pack stale.
3. The **Committed run / Live run** toggle switches between the two. Live runs never
   overwrite the committed outputs. Live results disappear when the server restarts.

The access code is an environment variable (`ACCESS_CODE`) on the server. It is not stored
in this repository.

## Stage to agent mapping

| Stage | Page | Live action | Runs |
|---|---|---|---|
| 1 Extract rules | rules summary, 73 rules with quotes | disabled | `extract-rules` skill (committed output only) |
| 2 Analysis | analytics headline cards, top-20 tables, audit history | disabled | `spend-analyst`, `findings-analyst` (committed output only) |
| 3 Risk register | register | **rerun** | `risk-assessor` with the `risk-assessment` skill |
| 4 Auditor gate | decision form | **form, then rerun** | writes `auditor-comments.md`, reruns `risk-assessor` (revision) |
| 5 Agent team | memo, matrix, program, challenges, review | disabled | `planner`, `challenger`, `qa-reviewer` (committed output only) |
| 6 Sign-off | sign-off form | **form (no model call)** | writes the sign-off block of `review.md` |

## Cost and safety controls

- **Model:** Sonnet (`claude-sonnet-5-5`), `max_turns` and a per-run dollar cap
  (`max_budget_usd`) on every job. Defaults: stage 3 at $0.35, stage 4 at $0.25.
- **One job at a time.** A second request gets "another live run is in progress".
- **Server-wide ledger.** Recorded spend is summed; once it would pass `LEDGER_CAP_USD`
  (default $4.00 of a $5 credit) the server refuses new runs and says so. The ledger is on
  the ephemeral disk, so it resets on a restart; the Anthropic console is the real balance.
- **Measured cost in testing:** stage 3 rebuild about $0.17 (46 s); stage 4 revision about
  $0.10 to $0.17 (15 to 35 s). A full demo of both is roughly $0.27.
- **Clear failure messages** for: credit exhausted, rate limit, cost cap hit, turn cap hit,
  timeout, killed process (probably memory), rejected key. A job only counts as finished
  if the new register was really written.
- **The API key** is read on the server only (from the environment, or a gitignored `.env`
  locally). It is removed from the server's own environment at start-up and passed only
  to the agent process; it is never sent to the browser or logged, and any `sk-ant-...`
  string is redacted from streamed output. The SDK's agent process runs with its own
  config folder, so it cannot touch another Claude login on the machine.
- **Agent sandboxing is mitigation, not a guarantee.** The agents have a shell. A hook
  denies commands that touch the environment, network or paths outside the run folder, and
  the Claude Code subprocess scrub setting is on to keep credentials out of shell
  commands. I did not independently prove the scrub hides the key; the access code is what
  really limits who can run an agent.
- **Wrong access codes** are rate-limited (5 per 10 minutes per client).

## Agent teams: what happened

The original run used Claude Code agent teams (planner, challenger and qa-reviewer
messaging each other). I tested a minimal two-teammate PING/PONG through the SDK with a
$0.20 cap; it did not finish within the cap, and each agent process alone used about
242 MB, so teams would not fit on the free server anyway. Stage 5 is therefore **not
rerunnable live** and shows the committed team output. If it is enabled later it will run
planner, challenger and qa-reviewer in sequence with the same messages (`PACK READY`,
challenges, `QA PASS/FAIL`, `DONE`), and the page will say it is a sequential fallback.

## Limits and honest expectations on Render's free tier

The free web service has 512 MB RAM, 0.1 CPU, sleeps after 15 minutes idle and has an
ephemeral disk.

- **Browsing always works.** It reads files baked into the image. After a sleep the first
  request takes about 30 to 60 seconds to wake the service. After any restart the live
  results and the ledger are gone and the page falls back to the committed run.
- **Memory.** Measured locally: the bundled agent CLI peaked at about 242 MB by itself,
  before FastAPI (about 60 MB) and the Python scripts the agent runs. Stages 3 and 4 are
  the lightest agent runs (`build_register.py` does not use pandas), so they *may* fit, but
  I could not test on a 512 MB machine, and they are the stages most likely to be killed
  with "the agent process was killed, probably out of memory". Stages 2 and 5 would be much
  more likely to fail, which is why they are switched off.
- **Speed.** At 0.1 CPU everything is slow. Locally a stage 3 rebuild took 46 seconds; on
  the free tier expect several times that, and a long wait before the first log line.
  Each run has a wall-clock limit of 15 minutes.
- **If live runs fail on the free tier**, the committed view is still complete. Moving the
  service to a paid instance (at least 1 GB) is the fix for memory and speed.
- **The Docker image was not built or run on my machine** (Docker is not installed there).
  The first build happens on Render. The image holds the Agent SDK's bundled agent
  binary (about 240 MB), so it is large for a free service.

Other limits: a live stage 3 rebuild produces a *different* register from the committed one
(the committed run rated 8 risks over a longer process; a fresh rebuild produced 6); the
data are three months of public spend and results are risk indicators to investigate,
never findings of wrongdoing.

## Run it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-server.txt
cp .env.example .env              # then edit .env: ANTHROPIC_API_KEY and ACCESS_CODE
.venv/bin/python -m uvicorn app.main:app --port 8000
# open http://localhost:8000
```

Needs `poppler-utils` and `jq` on the PATH for live runs. `.env` is gitignored and
excluded from the Docker image. Without a key or access code the site still works as a
read-only viewer. Unit tests (no model calls): `.venv/bin/python tests/test_gate_form.py`.

## Deploy

`Dockerfile` and `render.yaml` define a single Docker web service on the free plan.
Set `ANTHROPIC_API_KEY` and `ACCESS_CODE` in the Render dashboard (Environment). They are
declared in `render.yaml` with `sync: false`, so their values are never in the repo.

## Part B files

```
app/main.py        routes: read-only viewer API, gate form, sign-off, job stream
app/runner.py      working copy, one-job lock, Agent SDK options, error messages
app/guard.py       secrets, access code, cost ledger, redaction, tool hook
app/gate_form.py   decision-form and sign-off text transforms (no model call)
app/static/        the single page (vanilla JS; marked and DOMPurify vendored)
tests/             unit tests for the form logic and guards
Dockerfile  render.yaml  .env.example  requirements-server.txt
```
