# InsightFlow AI — Interview Preparation Guide

---

## 1. The Elevator Pitch (30 seconds)

> "InsightFlow AI is a multi-agent data analysis platform I built end-to-end — a user
> uploads a messy CSV or Excel file, and a graph of specialized AI agents cleans it
> with human approval at each step, runs exploratory data analysis, generates a
> formatted Word report with both technical and plain-language summaries, and lets
> the user ask natural-language questions about their data that get answered with
> real SQL queries and validated before being shown. It's built with LangGraph for
> orchestration, FastAPI for the backend, Postgres for persistent agent state, and a
> custom frontend — and it's fully deployed."

Memorize the shape of this, not the exact words. You should be able to say it
without sounding rehearsed.

---

## 2. The Full STAR-style Explanation (2-3 minutes, if asked to "walk me through it")

**Problem**: Data analysts spend a huge amount of time on repetitive, low-judgment
work — checking for missing values, fixing inconsistent formatting, generating
standard summary statistics — before they can even start answering real business
questions. I wanted to build something that automates the repetitive parts while
keeping a human in the loop for actual judgment calls, and then lets you just talk
to your data afterward.

**Solution**: I designed this as a **multi-agent system** rather than one big
prompt, because each stage needs a genuinely different kind of reasoning:
- A **cleaning agent** that detects issues (missing values, duplicates, type
  mismatches, invalid values, inconsistent categories) using deterministic pandas
  logic — no LLM needed for detection, since it's not a judgment call.
- A **human-in-the-loop step** using LangGraph's `interrupt()` — the graph
  genuinely pauses execution, persists its state to Postgres, and waits for the
  user to approve or choose an action per issue, then resumes exactly where it
  left off.
- An **EDA agent** that computes statistics, correlations, and generates charts.
- A **report generation agent** that uses an LLM to turn those raw numbers into
  two different tones of writing — a formal analyst-style findings section, and a
  separate plain-language summary for non-technical readers — then assembles both
  into an actual Word document.
- An **analyst agent** that classifies incoming questions as either a direct
  lookup or something requiring multi-step investigation, writes real SQL against
  the data using DuckDB, and answers grounded in actual query results — not
  hallucinated numbers.
- A **validator agent** that checks the analyst's answer against the real data
  before it's shown to the user, with a retry loop if it's rejected.

**Technology**: LangGraph for the agent graph and state management, Groq for LLM
inference, FastAPI for the backend API, PostgreSQL for checkpointed agent state
(so sessions can pause and resume across HTTP requests), DuckDB for querying
pandas dataframes with real SQL, python-docx for report generation, and a vanilla
HTML/CSS/JS frontend. Deployed on Render with Supabase Postgres.

**Impact/Outcome**: A fully working, deployed system that takes a user from "here's
a messy spreadsheet" to "here's a cleaned dataset, a written report, and answers to
my specific questions" — with meaningful guardrails (human approval on data
changes, answer validation before display) that a naive single-prompt chatbot
wouldn't have.

---

## 3. Questions by Category

### A. Architecture & Design Decisions (Foundational)

1. **Why did you use a multi-agent architecture instead of one big prompt?**
   Each stage requires different reasoning: cleaning detection is deterministic
   pandas logic (no LLM needed, cheaper and more reliable), report writing needs
   creative/narrative LLM generation, SQL generation needs code-writing ability,
   and validation needs a *different pass* checking the first pass's work — a
   single prompt can't cleanly separate these responsibilities or be debugged
   independently.

2. **Walk me through the graph structure.**
   Be ready to sketch it: `START → cleaning_agent → HITL (interrupt) →
   apply_cleaning → [loop back to cleaning_agent, or proceed] → eda_agent →
   report_generation → [analyst_agent / final_agent / end]`, with
   `analyst_agent → validator_agent → [retry or show_answer]` as a sub-loop.
   Mention that a later redesign introduced a dispatcher pattern so each user
   action (clean / ask a question / generate report / email) could be triggered
   independently rather than forcing one linear path.

3. **Why LangGraph specifically, and not just LangChain agents or raw function
   calling?**
   LangGraph gives explicit control over state transitions, native support for
   loops (the cleaning retry loop, the validator retry loop), and — critically —
   `interrupt()` with checkpointing, which lets a workflow genuinely pause mid-
   execution and resume later from an entirely different HTTP request. That's not
   something you get for free with a simple agent loop.

4. **What is `interrupt()` and how does it actually work under the hood?**
   It's a LangGraph primitive that, when called inside a node, throws a special
   exception that the graph runtime catches. Instead of crashing, the runtime
   writes the current state to the checkpointer (Postgres, in my case) and
   returns control to the caller. Later, calling `.invoke(Command(resume=...))`
   with the same `thread_id` picks the exact same node back up, with the
   `interrupt()` call now returning whatever value was passed into `resume`.

5. **Why Postgres for checkpointing instead of in-memory state?**
   In-memory state dies when the server restarts or across separate requests —
   since my HITL flow means a user's session might pause for minutes while they
   decide on cleaning actions, and the FastAPI process needs to be stateless
   between requests, the graph's state has to be durably persisted somewhere
   external. Postgres via LangGraph's `PostgresSaver` checkpointer solves this.

6. **What's a `thread_id` and why does it matter?**
   It's the key that ties together a specific user's ongoing conversation with
   the graph — I use one UUID per upload session, so it's also used as the
   folder name for that user's files and as the checkpoint identifier in
   Postgres. This lets multiple users use the app concurrently without their
   state colliding.

### B. Human-in-the-Loop & Data Cleaning (Core differentiator — expect deep questions here)

7. **Why not just auto-clean the data without asking the user?**
   Data cleaning decisions are genuinely subjective — whether to drop a row with
   a missing value or fill it with the mean depends on context the system
   doesn't have. Auto-cleaning silently could also produce misleading results the
   user doesn't know about. HITL keeps the user in control of decisions that
   affect their actual conclusions.

8. **How does your cleaning agent detect issues? Walk me through the logic for
   one detector.**
   Example: for type mismatches, I don't trust the column's current pandas
   dtype — I attempt `pd.to_numeric()`/`pd.to_datetime()` conversion with
   `errors='coerce'` on every column, and measure what percentage of values
   convert successfully. If a high percentage converts, I flag it as "this
   column is probably meant to be numeric/date but has some bad entries," rather
   than assuming based on dtype alone (which is unreliable on messy CSVs).

9. **How do you handle the fact that different issues need different fix
   strategies?**
   Every detected issue gets a stable, predictable ID (e.g.
   `missing_values_Age`). The user's decision is a dict mapping issue IDs to
   chosen actions (`fill_mean`, `drop_rows`, `convert_to_numeric`, etc.) — a
   dispatch loop in the apply step reads each issue, looks up the chosen action
   by ID, and calls the matching pandas function. Anything not explicitly
   addressed defaults to "skip."

10. **How does the iterative cleaning loop work — can a user clean in multiple
    rounds?**
    Yes — after applying approved fixes, the cleaning agent re-runs detection on
    the *already-cleaned* file (not the original), so any remaining or newly
    visible issues show up fresh. A conditional edge checks a `proceed_to_eda`
    flag the user sets each round to decide whether to loop back or move on.

11. **What was the hardest bug you hit with the HITL implementation?**
    (Great story to have ready — see Section 5, "War Stories.")

12. **How would you handle a numeric threshold that behaves badly on small
    datasets?**
    I hit exactly this — my "invalid negative values" detector used a pure
    percentage threshold, which is fragile on small samples (one row can swing
    the percentage by 10+ points). I fixed it with a hybrid rule: flag if the
    percentage is low **or** the absolute count is very small, so it works
    sensibly on both large and small datasets.

### C. LLM Usage & Prompt Engineering

13. **Where exactly does the LLM get used in this project, and where does it
    deliberately NOT get used?**
    Used for: classifying question type, generating SQL from natural language,
    writing the analytical findings and plain-language summary, validating
    answers. NOT used for: cleaning issue detection, statistics computation,
    chart generation — these are deterministic and cheaper/more reliable as
    plain code. Being able to explain *why* something didn't need an LLM is a
    strong signal of good judgment.

14. **How do you prevent the LLM from hallucinating numbers in the report?**
    The prompt explicitly instructs it to only reference numbers provided in the
    context, and I keep temperature low (0.3) for report generation, since
    creativity isn't valuable there — grounding is.

15. **Why two separate LLM calls for the report instead of one?**
    I wanted genuinely different tones — a formal analyst voice and an
    accessible plain-language voice — and found that asking one prompt to
    produce both in a single response tends to blur the tones together. Two
    focused calls with distinct instructions gave a cleaner separation, and the
    plain-language call reuses the *already-generated* findings rather than raw
    numbers, so it's a cheap rephrasing step, not a second independent analysis.

16. **How does the analyst agent decide between a direct SQL answer and a
    multi-step investigation?**
    A classification LLM call reads the question and returns "direct" or
    "investigative." Direct questions become one SQL query. Investigative
    questions ("why is X happening") get broken into 2-4 sub-questions by the
    LLM, each becomes its own SQL query, and a final LLM call synthesizes all
    the sub-results into one answer.

17. **What is DuckDB doing in this project, and why not just use pandas
    directly?**
    DuckDB lets me run real SQL directly against an in-memory pandas DataFrame,
    which is a much more natural fit for LLM-generated queries than trying to
    have the LLM write pandas method chains. It automatically recognizes a
    DataFrame variable in scope and treats it like a SQL table.

18. **Why didn't you let the LLM write and execute arbitrary Python/pandas code
    for analysis?**
    That's a real security/reliability risk — arbitrary LLM-generated code
    execution needs a sandbox (like E2B) to be done safely, since you can't
    fully predict or validate what it'll do. I scoped this project to SQL-only
    generation specifically because SQL is easier to constrain and reason about
    than arbitrary code execution, and explicitly decided sandboxed code
    execution was future scope rather than something to half-implement.

### D. Validation & Reliability

19. **What does the validator agent actually check, and what happens if it
    rejects an answer?**
    It's given the question, the answer, and the supporting data, and asked
    whether the answer is actually supported by that data without invented
    numbers. If rejected, the graph loops back to the analyst agent for another
    attempt, capped at a small retry count to avoid infinite loops — after which
    it shows the best available answer, flagged as unverified rather than
    hidden.

20. **Isn't using an LLM to validate another LLM's output a bit circular?**
    Fair critique — it's not a perfect guarantee, but it's a genuinely useful
    second pass: it's evaluating a narrow, specific claim ("does this text match
    this data") rather than generating from scratch, which is a much easier and
    more reliable task than the original generation. It's a real quality
    improvement, not a bulletproof one — I'd frame it honestly as reducing
    error rate, not eliminating it.

21. **How would you evaluate whether this system's answers are actually
    accurate, systematically rather than anecdotally?**
    (Good one to think about even though I didn't build it: a held-out set of
    question/expected-answer pairs, run through the pipeline, scored against
    ground truth — this is the natural "future work" answer.)

### E. Backend / API Design

22. **Why FastAPI, and how does it interact with the LangGraph workflow?**
    FastAPI exposes the graph as HTTP endpoints — upload starts a graph run,
    resume endpoints send `Command(resume=...)` calls back into paused threads,
    and download/email endpoints read directly from checkpointed state without
    needing the graph to be "at" any particular point, since files are saved to
    disk and referenced by path in state.

23. **How do you get the "next pending interrupt" out of a graph — walk me
    through that.**
    I initially returned `result["__interrupt__"]` directly from `.invoke()`,
    but hit a real bug where this came back empty even though the graph had
    genuinely paused. The reliable fix was reading from
    `workflow.get_state(config).tasks`, checking each task's `.interrupts`
    attribute — this is a more explicit, dependable way to check "what is this
    thread currently waiting on" than trusting the invoke return value alone.

24. **How does file handling work — what happens to an uploaded file?**
    Each session gets a UUID, used as both the LangGraph thread_id and a folder
    name under `uploads/`. The raw file is saved there, and every downstream
    node (cleaning, report generation) saves its output back into that same
    folder, with only the *path* (never the actual data) stored in graph state,
    since state needs to remain JSON-serializable and checkpoint-safe.

25. **How would this need to change to support many concurrent users in
    production?**
    A few real answers: connection pooling for Postgres (which I already used,
    `psycopg_pool.ConnectionPool`, instead of a single bare connection — I hit a
    real bug from using a bare connection under concurrent load), moving file
    storage to something like S3 instead of local disk (since Render's
    filesystem isn't necessarily persistent across deploys/restarts), and adding
    rate limiting on LLM calls.

### F. Debugging War Stories (Have 2-3 of these ready in detail — see Section 5)

26. Tell me about a bug that took you a long time to figure out.
27. Tell me about a time your assumptions about a library's behavior were wrong.
28. What was the biggest architecture change you made mid-project, and why?

### G. Deployment & Infra

29. **What's your deployment stack, and why those choices?**
    FastAPI backend on Render, PostgreSQL on Supabase, static frontend also on
    Render — chosen mainly for generous free tiers suitable for a portfolio
    project. CORS is explicitly configured to allow the frontend's origin.

30. **What issues did you hit during deployment?**
    A Python 3.14 default on Render had no prebuilt wheels for some C-extension
    dependencies (pydantic-core), causing a Rust compilation failure in a
    read-only build environment — fixed by pinning Python 3.11 via
    `runtime.txt`. Also hit a numpy/pandas version resolution conflict, solved
    by relaxing exact pins to compatible ranges.

31. **What would you do differently if you were deploying this for real users,
    not a portfolio demo?**
    Verify a real sending domain for email instead of test-mode-only, move file
    storage off local disk, add authentication/session ownership checks (right
    now anyone with a `session_id` could access that session's data — a real
    security gap worth naming honestly if asked), add structured logging and
    monitoring, and add automated tests around the graph logic.

### H. Frontend

32. **Why vanilla HTML/CSS/JS instead of a framework?**
    Kept the frontend dependency-free and simple to deploy as static files with
    no build step, which was a pragmatic choice given the backend complexity
    was the primary learning focus of this project.

33. **How does the frontend know what UI to render at any given moment?**
    Every backend response includes an `interrupt` payload (when the graph is
    paused) with a `type` field — `"approval"` for cleaning decisions,
    `"router_check"` or similar for next-step choices — and the frontend
    branches its rendering based on that type, building the appropriate form or
    button set dynamically.

### I. General "Prove You Understand This, Not Just Built It" Questions

34. What would break if two users uploaded files at the exact same time? How
    does your design prevent their data from mixing?
35. If a cleaning issue's ID collided with another issue's ID, what would
    happen? How did you prevent that?
36. Why does `cleaning_agent` need to check whether a cleaned file already
    exists before deciding what to load?
37. What's the difference between resuming a LangGraph thread and starting a
    fresh one, and how does your code decide which happens?
38. If Groq's API went down, what would happen to your app? How would you make
    it more resilient? (Good opening to mention the planned-but-not-built
    Claude/GPT fallback idea from your original stack design.)
39. Why is `NaN` a valid pandas/numpy value but not valid JSON, and where did
    that bite you in this project?
40. What's the security risk in generating SQL from user input via an LLM, and
    what did you do (or could you do) to mitigate it?

---

## 4. Questions YOU Should Ask an Interviewer (shows engagement, not just answering)

- "What does your team currently use for agent orchestration — anything like
  LangGraph, or a custom setup?"
- "How do you handle human-in-the-loop patterns in production agent systems, if
  at all?"
- "What's your approach to validating LLM outputs before they reach users?"

---

## 5. War Stories — Prepare These in Full Detail (interviewers love these)

**Story 1: The silent `interrupt()` bug.**
Everything looked correct — code reviewed clean, graph wiring matched a working
test script — but under FastAPI, `interrupt()` appeared to just... not interrupt.
No crash, no error, the node ran and then nothing. Systematically ruled out
causes: added debug prints (confirmed the node *was* being called), checked the
checkpointer connection (switched from a single bare `psycopg.connect()` to a
proper `ConnectionPool`, since a single connection isn't safe under a
multi-request server), and finally discovered via `workflow.get_state(config)`
that the pause *was* actually happening — I'd just been reading the interrupt
data from the wrong place (`result["__interrupt__"]` on the plain invoke return,
instead of `get_state().tasks[i].interrupts`). Lesson: when a library's
documented pattern doesn't seem to work, verify your assumption about *where*
the data should appear before assuming the mechanism itself is broken.

**Story 2: The threshold that only failed on small data.**
A negative-value detector using a straight 10% threshold worked fine in every
test until it silently failed to flag a single negative value in a 9-row
column — because 1/9 is 11%, just over the line. This taught me that
percentage-based thresholds are fundamentally unreliable on small samples, and I
redesigned it as a hybrid rule (percentage OR absolute count) — a small fix, but
one that reflects a real, generalizable data science principle.

**Story 3: The NaN-to-JSON crash.**
A SQL query legitimately returned a missing value as `NaN` (a numpy/pandas
concept), which is *not* valid JSON — and my Postgres checkpointer, trying to
serialize that state, crashed with an opaque `psycopg.errors.InvalidTextRepresentation`
error. Fixed by explicitly replacing NaN/inf values with `None` (JSON `null`)
before any pandas result gets stored in graph state — and recognized this as a
recurring pattern (I'd already hit a similar numpy-type issue with `.describe()`
output earlier), which pushed me toward being more disciplined about sanitizing
pandas/numpy output at every boundary where it enters state.

---

## 6. Quick-Reference Cheat Sheet (skim this 10 minutes before the interview)

- **Project**: multi-agent data analysis platform, upload → clean → EDA → report → Q&A
- **Core tech**: LangGraph (orchestration), FastAPI (backend), Postgres (checkpointing),
  Groq (LLM), DuckDB (SQL on dataframes), python-docx (reports)
- **Key differentiator**: human-in-the-loop cleaning + validator agent with retry —
  not just a single-shot chatbot wrapper
- **Hardest bug**: interrupt not surfacing correctly through FastAPI — fixed via
  `get_state().tasks`, not the plain invoke return
- **Deliberate scope cuts**: no arbitrary LLM code execution (security), no auth
  (portfolio scope), test-mode email only (no verified domain)
- **What you'd improve with more time**: S3 storage instead of local disk, auth/session
  ownership, automated evals for answer accuracy, LLM provider fallback
