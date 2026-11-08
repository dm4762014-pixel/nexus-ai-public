from pathlib import Path
from ollama import chat
from openpyxl import Workbook, load_workbook

MODEL = "qwen3:1.7b"
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def create_study_timetable(subjects: str) -> str:
    """Create a real 7-day Excel study timetable.

    Args:
        subjects: Comma-separated subjects to schedule.
    """
    items = [s.strip() for s in subjects.split(",") if s.strip()]

    if not 1 <= len(items) <= 8:
        raise ValueError("Provide 1 to 8 subjects")

    for item in items:
        if len(item) > 50 or item.startswith(("=", "+", "-", "@")):
            raise ValueError("Invalid subject")

    wb = Workbook()
    ws = wb.active
    ws.title = "Study Plan"

    ws.append(["Day", "Subject", "Activity", "Minutes"])

    activities = [
        "Learn basic concepts",
        "Read notes and examples",
        "Practice exercises",
        "Solve problems",
        "Review key topics",
        "Complete practical tasks",
        "Revise and self-test",
    ]

    for i in range(7):
        ws.append([
            f"Day {i + 1}",
            items[i % len(items)],
            activities[i],
            60,
        ])

    ws.column_dimensions["A"].width = 15
    ws.column_dimensions["B"].width = 25
    ws.column_dimensions["C"].width = 32
    ws.column_dimensions["D"].width = 15

    path = OUTPUT_DIR / "NTTF_7_Day_Study_Plan.xlsx"
    wb.save(path)

    # Independently verify the saved workbook.
    check = load_workbook(path, read_only=True)
    sheet = check.active
    rows = list(sheet.iter_rows(values_only=True))
    valid = (
        len(rows) == 8
        and all(row[3] == 60 for row in rows[1:])
    )
    check.close()

    if not valid:
        raise RuntimeError("Workbook verification failed")

    return f"Excel file created and verified: {path}"


print("NEXUS AI: Starting first real agent task...")

messages = [
    {
        "role": "system",
        "content": (
            "You are NEXUS AI, a tool-using assistant. "
            "When asked to create a timetable, you MUST "
            "call create_study_timetable. Provide subjects "
            "as a single comma-separated string. "
            "Do not claim success without executing the tool."
        ),
    },
    {
        "role": "user",
        "content": (
            "Create a 7-day Excel study timetable for "
            "Python, Linux, Networking, Cybersecurity."
        ),
    },
]

response = chat(
    model=MODEL,
    messages=messages,
    tools=[create_study_timetable],
    think=False,
    options={"num_ctx": 2048, "num_predict": 384},
    keep_alive="30s",
)

calls = response.message.tool_calls or []

if len(calls) != 1:
    print("AI did not make exactly one tool call.")
    print("Model response:", response.message.content)
else:
    call = calls[0]

    if call.function.name != "create_study_timetable":
        print("Rejected unapproved tool:", call.function.name)
    else:
        print("AI selected tool:", call.function.name)
        print("Arguments:", call.function.arguments)

        try:
            subjects = call.function.arguments.get("subjects")
            if not isinstance(subjects, str):
                raise ValueError("Subjects must be a string")

            result = create_study_timetable(subjects)
            print("SUCCESS:", result)
        except Exception as error:
            print("TOOL ERROR:", error)
