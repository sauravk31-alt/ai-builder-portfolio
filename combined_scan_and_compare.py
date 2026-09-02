"""
Exam Finder India - Combined Scanning + Comparison Agent
Gemini handles search AND structured comparison in a single call per exam,
replacing the split (API search + local model compare) architecture after
repeated local-model testing showed the comparison step needed capability
the local models on this hardware couldn't reliably provide.

Produces:
- flagged_updates.csv  -> real detected changes, for manual review only
- exams_cleaned.csv    -> last_verified_date updated for every exam checked
"""

import os
import json
import time
import math
import pandas as pd
from datetime import date
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch, UrlContext

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

BATCH_SIZE = 3
BATCH_STATE_FILE = "batch_state.json"
DATA_FILE = "exams_cleaned.csv"
FLAGGED_FILE = "flagged_updates.csv"
MODEL = "gemini-3.5-flash-lite"


def get_next_batch(df):
    active = df[df["status"] == "Active"].reset_index(drop=True)
    if os.path.exists(BATCH_STATE_FILE):
        with open(BATCH_STATE_FILE) as f:
            start = json.load(f).get("last_index", 0)
    else:
        start = 0
    end = start + BATCH_SIZE
    batch = active.iloc[start:end]
    if len(batch) < BATCH_SIZE:
        remaining = BATCH_SIZE - len(batch)
        batch = pd.concat([batch, active.iloc[0:remaining]])
        next_start = remaining
    else:
        next_start = end % len(active)
    with open(BATCH_STATE_FILE, "w") as f:
        json.dump({"last_index": next_start}, f)
    return batch


def clean_value(val):
    """Prevents pandas NaN from silently rendering as the literal text 'nan'
    in the prompt, which was causing the model to treat missing deadlines
    as an existing (if odd) value rather than genuinely absent data."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return "NOT RECORDED"
    val_str = str(val).strip()
    if val_str.lower() in ("nan", ""):
        return "NOT RECORDED"
    return val_str


def build_prompt(row):
    return f"""You are checking the current status of an exam listing for a student information website, and comparing it against our existing database record. Do not guess or fabricate information - only report what you actually find.

CURRENT DATABASE RECORD:
- application_deadline: {clean_value(row.get('application_deadline'))}
- min_qualification: {clean_value(row.get('min_qualification'))}
- stream_requirement: {clean_value(row.get('stream_requirement'))}
- scope: {clean_value(row.get('scope'))}
- eligible_states: {clean_value(row.get('eligible_states'))}
- domicile_reservation_state: {clean_value(row.get('domicile_reservation_state'))}
- Source URL on file: {row.get('source_url', 'NONE PROVIDED')}

SEARCH INSTRUCTIONS:
1. If a source URL is provided, check it directly for the current official notification.
2. If that URL is a general homepage/index page without specific admission details, search that same website for the current admission notification page.
3. If no source URL is provided, or it appears broken/outdated, use a general web search for this exam's official current notification.

COMPARISON RULES - apply these strictly:
1. If your search does NOT surface information about a field, do NOT report it as changed. Silence is not evidence of change.
2. A qualification requirement is the SAME if the core credential level is unchanged (e.g. "Class 10", "Class 12", "Bachelor's Degree"). Extra detail like marks percentages or "from a recognized board" is NOT a change to min_qualification - put such detail in a separate field called qualification_details_note instead.
3. Never put information about one field into a different field's value.
4. Only include a field in your output if its value has GENUINELY changed. Do NOT list fields that are confirmed unchanged - report ONLY real changes.
5. Domicile-based reservations are frequently missed - check carefully whether the source mentions any seats reserved for a specific state/UT/institution, separate from general eligibility.
6. IMPORTANT: if a field's current value is "NOT RECORDED" and your search finds ANY real value for it (a specific deadline, a specific eligibility detail, etc.), this ALWAYS counts as a genuine change worth reporting - filling in previously missing data is exactly as important as correcting an outdated value. Do not skip this just because there was no prior value to differ from.

Respond with ONLY a JSON list of genuine changes (empty list [] if none), plus a source/confidence record, in this exact format:
{{
  "changes": [
    {{"field_changed": "...", "old_value": "...", "new_value": "...", "reason": "..."}}
  ],
  "check_method": "anchored" | "anchored_with_site_search" | "open_search" | "source_broken",
  "confidence": "high" | "medium" | "low",
  "source_used": "..."
}}"""


def check_exam(row):
    response = client.models.generate_content(
        model=MODEL,
        contents=build_prompt(row),
        config=GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch()), Tool(url_context=UrlContext())],
        ),
    )

    raw_text = response.text.strip()
    # Extract JSON by finding the outermost { } pair, rather than splitting on
    # ``` fences - splitting on backticks broke if the model's response text
    # happened to contain a ``` sequence anywhere inside a string value.
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        raw_text = raw_text[start:end + 1]

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        print(f"  [PARSE ERROR - raw output below]\n{raw_text[:500]}\n")
        return {"changes": [], "check_method": "parse_error", "confidence": "low",
                "source_used": None, "_raw": raw_text[:300]}


def main():
    exams_df = pd.read_csv(DATA_FILE)
    batch = get_next_batch(exams_df)
    today_str = str(date.today())

    print(f"Checking {len(batch)} exams: {', '.join(batch['exam_name'].tolist())}\n")

    flagged_rows = []

    for _, row in batch.iterrows():
        print(f"Checking: {row['exam_name']}...")
        result = check_exam(row)

        real_changes = [
            c for c in result.get("changes", [])
            if str(c.get("old_value", "")).strip() != str(c.get("new_value", "")).strip()
        ]

        for change in real_changes:
            flagged_rows.append({
                "exam_name": row["exam_name"],
                "field_changed": change.get("field_changed", ""),
                "old_value": change.get("old_value", ""),
                "new_value": change.get("new_value", ""),
                "reason": change.get("reason", ""),
                "source_checked": result.get("source_used", ""),
                "confidence": result.get("confidence", ""),
                "check_method": result.get("check_method", ""),
                "date_checked": today_str,
            })

        print(f"  -> {len(real_changes)} genuine change(s), confidence: {result.get('confidence')}, method: {result.get('check_method')}\n")

        exams_df.loc[exams_df["exam_name"] == row["exam_name"], "last_verified_date"] = today_str
        time.sleep(6)

    if flagged_rows:
        new_flagged_df = pd.DataFrame(flagged_rows)
        try:
            existing = pd.read_csv(FLAGGED_FILE)
            new_flagged_df = pd.concat([existing, new_flagged_df], ignore_index=True)
        except FileNotFoundError:
            pass
        new_flagged_df.to_csv(FLAGGED_FILE, index=False)
        print(f"Saved {len(flagged_rows)} flagged change(s) to {FLAGGED_FILE}")
    else:
        print("No changes flagged this run.")

    exams_df.to_csv(DATA_FILE, index=False)
    print(f"Updated last_verified_date for {len(batch)} exam(s).")


if __name__ == "__main__":
    main()
