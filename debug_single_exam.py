"""
Debug tool: run the exact same check on ONE specific exam and print the
FULL raw model response - not just the parsed "changes" count - so we can
see whether the model found deadline info and simply didn't report it,
or genuinely found nothing.

Usage: python debug_single_exam.py "NEET-UG (Medical/Dental Entrance)"
"""

import os
import sys
import pandas as pd
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch, UrlContext
from combined_scan_and_compare import build_prompt, MODEL  # reuse the real prompt logic

client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))


def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_single_exam.py \"Exact Exam Name\"")
        return

    exam_name = sys.argv[1]
    df = pd.read_csv("exams_cleaned.csv")
    matches = df[df["exam_name"] == exam_name]

    if matches.empty:
        print(f"No exam found matching: {exam_name}")
        print("Available names containing similar text:")
        similar = df[df["exam_name"].str.contains(exam_name.split()[0], case=False, na=False)]
        print(similar["exam_name"].tolist())
        return

    row = matches.iloc[0]
    prompt = build_prompt(row)

    print("=" * 70)
    print("PROMPT SENT:")
    print("=" * 70)
    print(prompt)
    print("\n" + "=" * 70)
    print("FULL RAW MODEL RESPONSE:")
    print("=" * 70)

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=GenerateContentConfig(
            tools=[Tool(google_search=GoogleSearch()), Tool(url_context=UrlContext())],
        ),
    )
    print(response.text)


if __name__ == "__main__":
    main()
