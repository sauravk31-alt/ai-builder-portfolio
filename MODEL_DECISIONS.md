# Model Architecture Decisions — Exam Finder India

This document describes how models were evaluated and selected for this project, including a real architecture revision made after production testing revealed a local-model limitation.

## Requirements for the Project
- Extract details such as exam name, academic eligibility, and domicile eligibility from text.
- Able to do web browsing (for keeping exam data current).
- Provide structured output.
- Be economical to scale.

Based on these criteria, it was established early that frontier-level reasoning is not required for this task.

## Data Volume
- ~100 exam records tracked.
- Updates checked twice a week, balancing freshness against cost.
- Queries batched (originally 5, later reduced to 3 during testing) to avoid overloading a single call and to isolate failures.

## Key Finding: Schema Design vs. Model Capability

Initial testing used a field literally named `state`, which every model tested — local (Qwen 2.5:7B, Gemma2:2B) and API (Claude Haiku 4.5, Gemini) alike — misread as "the applicant's home state," collapsing a nationally-open exam (MHT-CET) to `state: Maharashtra` despite it being open to all-India applicants with only reserved seats for Maharashtra domicile students.

Renaming the field to explicitly separate general eligibility from domicile-based reservation resolved this across every model tested, including the smallest local model. **Conclusion: this specific failure was a schema design issue, not a model capability limitation** — an important distinction that shaped the final database schema (`scope`, `eligible_states`, and `domicile_reservation_state` as three distinct fields).

## Model Evaluation

**Claude Haiku 4.5**
- Correct extraction on test cases.
- Token economics: input $1/MTok, output $5/MTok — estimated $0.64–1.28/month for this workload at twice-weekly, batched calls (Batch API discount applied).

**Gemini (3.6 Flash → 3.5 Flash-Lite, final)**
- Correct extraction on test cases.
- Free tier initially targeted for cost reasons, but this proved unsuitable in production (see Architecture Revision below).
- Now running on Tier 1 (billing enabled) at negligible real cost, consistent with the original cost estimate.

**Local LLMs tested for extraction (initial round):** Qwen 2.5:7B and Gemma2:2B, both on an 8GB VRAM consumer GPU. Both performed correct extraction once the schema fix above was applied — no meaningful quality gap between the two at this task.

## Architecture Revision: From Split (API + Local) to API-Only

**Original architecture:** the API model handled live web search only; a local model handled comparison against the existing database and structured output, to minimize API token cost. This was the planned production design.

**Free tier limitations encountered:** the first implementation used Gemini's free tier, which hit a hard **20 requests-per-day cap** on Flash-tier models — a genuine capacity ceiling, not occasional throttling, and incompatible with a scheduled, repeating job. A further complication was discovered: the AI Studio playground and the programmatic API key appeared to draw from **different quota allocations** for search-grounding tools specifically, meaning playground testing succeeded while identical API calls failed. Billing was enabled (Tier 1) to resolve this, at a real cost of pennies per month, consistent with the Week 3 cost analysis.

**Local model testing for comparison/structuring:** with API access resolved, the local-model comparison step (comparing Gemini's raw findings against the existing database record) was tested extensively across `gemma2:2b`, `qwen2.5:7b`, `qwen3.5:9b`, `qwen3.5:4b`, and `gemma4:e2b` (the larger Qwen variants were dropped due to VRAM pressure and impractically slow inference on this hardware). Across every model tested, the same task produced unreliable results:
- False positives — flagging paraphrased or more-detailed-but-substantively-unchanged text as a real change.
- Field scrambling — e.g., a domicile reservation detail bleeding into the `scope` field instead of its own field.
- A recurring failure to distinguish "the new information doesn't mention this field" from "this field has changed."

Targeted prompt refinements (explicit rules, worked examples, a dedicated `qualification_details_note` field to avoid forcing a same-vs-different judgment call) narrowed some of these failure modes but did not eliminate them across model sizes from 2B to 9B parameters. This suggested the core issue was the two-stage handoff itself — structured data being flattened to free text by one model, then reconstructed by a second, smaller model — rather than any single local model's raw capability.

**Final architecture:** search, URL-context following, and structured comparison output were consolidated into a **single Gemini call per exam**, removing the local comparison step entirely. This is not a meaningfully more expensive design than originally planned — the API call was already being made for search; it now also returns structured output directly rather than raw prose, avoiding a second model call altogether. Testing on this combined approach surfaced two real code-level bugs, both fixed once identified:
- A literal `"nan"` string (from pandas' representation of blank cells) being read by the model as an actual value rather than "missing," suppressing legitimate updates to blank fields.
- A fragile markdown-fence-stripping approach that could corrupt valid JSON if the model's response happened to contain a stray ``` sequence inside a text field — replaced with robust brace-matching extraction.

One further finding, explicitly **not** treated as a bug: the model showed occasional non-determinism — the same exam and prompt occasionally returned an incomplete result on one run and a complete one on a retry (confirmed via direct side-by-side testing with no code changes between runs). Rather than chase perfect single-pass reliability, the system's cyclic re-verification schedule (every active exam re-checked roughly every two weeks) is designed to absorb this, accepting eventual consistency over guaranteed per-run accuracy.

## Rationale for Final Design
- A single, well-instructed frontier-adjacent model (Gemini 3.5 Flash-Lite) handling search-to-structured-output in one call proved more reliable than splitting the task across a weaker local model, despite the split's original cost-saving intent.
- The cost difference between the split and consolidated approaches is negligible at this project's scale (~$1–2/month either way).
- Local models remain viable for other parts of this project (e.g., Project 2's ranking/summarization, which does not require this kind of cross-referencing judgment call) — this finding is scoped specifically to the comparison-against-structured-database task, not local models in general.

## What I'd Revisit
- **API model choice:** if Gemini becomes unavailable or underperforms at larger data volumes.
- **Batch size:** if quality issues emerge that suggest batches need to shrink further.
- **Twice-weekly cadence:** if the site gains a larger user base and freshness becomes more critical than cost.
- **Consolidated architecture:** if per-call costs rise significantly at scale, revisiting a split design may become worthwhile again — this decision was made under current, real cost data, not as a permanent architectural law.
