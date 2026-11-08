from pathlib import Path
from uuid import uuid4
from threading import Lock
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from ollama import chat
from openpyxl import Workbook, load_workbook

app = FastAPI(title="NEXUS AI")
MODEL = "qwen3:1.7b"
OUTPUT = Path(__file__).parent / "outputs"
OUTPUT.mkdir(exist_ok=True)
task_lock = Lock()


class Task(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)


def create_study_timetable(subjects: str) -> str:
    """Create a seven-day Excel study timetable.

    Args:
        subjects: Comma-separated names of subjects.
    """
    items = [x.strip() for x in subjects.split(",")]
    if not 1 <= len(items) <= 8:
        raise ValueError("Use 1 to 8 subjects")

    if any(not re.fullmatch(
        r"[A-Za-z0-9 .&/_-]{1,50}", x
    ) for x in items):
        raise ValueError("Invalid subject name")

    wb = Workbook()
    ws = wb.active
    ws.title = "Study Plan"
    ws.append(["Day", "Subject", "Activity", "Minutes"])

    activities = [
        "Learn concepts", "Read notes", "Practice",
        "Solve exercises", "Revise", "Practical work",
        "Self-test"
    ]

    for i in range(7):
        ws.append([
            f"Day {i + 1}",
            items[i % len(items)],
            activities[i],
            60
        ])

    for col, width in {
        "A": 15, "B": 25, "C": 28, "D": 15
    }.items():
        ws.column_dimensions[col].width = width

    file_id = uuid4().hex
    path = OUTPUT / f"{file_id}.xlsx"
    wb.save(path)

    check = load_workbook(path, read_only=True)
    rows = list(check.active.iter_rows(values_only=True))
    valid = (
        len(rows) == 8
        and all(r[3] == 60 for r in rows[1:])
    )
    check.close()

    if not valid:
        path.unlink(missing_ok=True)
        raise RuntimeError("Verification failed")

    return file_id


@app.post("/api/ask")
def ask(task: Task):
    if not task_lock.acquire(blocking=False):
        raise HTTPException(409, "Another task is running")

    try:
        response = chat(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are NEXUS AI. Answer clearly. "
                        "When asked to create a study timetable, "
                        "call create_study_timetable with "
                        "comma-separated subjects. "
                        "Never claim a file was created "
                        "unless the tool was executed. "
                        "Do not claim access to unavailable tools."
                    )
                },
                {"role": "user", "content": task.prompt}
            ],
            tools=[create_study_timetable],
            think=False,
            options={"num_ctx": 2048, "num_predict": 384},
            keep_alive="30s"
        )

        calls = response.message.tool_calls or []

        if calls:
            if len(calls) != 1:
                return {
                    "answer": "Unexpected tool requests.",
                    "file_url": None
                }

            call = calls[0]
            if call.function.name != "create_study_timetable":
                return {
                    "answer": "Tool not authorized.",
                    "file_url": None
                }

            try:
                subjects = call.function.arguments.get("subjects")
                if not isinstance(subjects, str):
                    raise ValueError("Invalid subjects")

                file_id = create_study_timetable(subjects)
                return {
                    "answer": (
                        "Excel timetable successfully "
                        "created and verified."
                    ),
                    "file_url": f"/api/files/{file_id}"
                }
            except Exception as error:
                return {
                    "answer": f"Tool failed: {error}",
                    "file_url": None
                }

        if "timetable" in task.prompt.lower() and (
            "create" in task.prompt.lower()
            or "make" in task.prompt.lower()
        ):
            return {
                "answer": (
                    "The AI did not call the Excel tool. "
                    "No file was created. Please retry."
                ),
                "file_url": None
            }

        return {
            "answer": response.message.content or "No response.",
            "file_url": None
        }

    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"AI request failed: {error}"
        )
    finally:
        task_lock.release()


@app.get("/api/files/{file_id}")
def download_file(file_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", file_id):
        raise HTTPException(400, "Invalid file ID")

    path = OUTPUT / f"{file_id}.xlsx"
    if not path.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(
        path,
        filename="NEXUS_Study_Plan.xlsx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )
    )


PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">
<title>NEXUS AI</title>
<style>
*{box-sizing:border-box}
body{
 margin:0;background:#080d1d;color:#edf3ff;
 font-family:Segoe UI,Arial,sans-serif
}
header{
 padding:22px;border-bottom:1px solid #253354;
 background:#10182d
}
h1{margin:0;color:#7caaff;font-size:27px}
header p{color:#a9b8d6;margin:8px 0 0}
main{max-width:880px;margin:45px auto;padding:20px}
.panel{
 background:#131e35;border:1px solid #334367;
 padding:25px;border-radius:17px
}
h2{margin-top:0;font-size:22px}
textarea{
 display:block;width:100%;height:125px;
 background:#0a1225;color:white;
 border:1px solid #42567f;border-radius:10px;
 padding:15px;font:16px Segoe UI,Arial;
 resize:vertical
}
button{
 margin-top:16px;background:#5869f2;
 border:0;border-radius:9px;color:white;
 padding:13px 27px;font-size:16px;cursor:pointer
}
button:disabled{opacity:.5;cursor:wait}
#result{
 white-space:pre-wrap;overflow-wrap:anywhere;
 line-height:1.6;margin-top:22px;
 padding:18px;border-radius:10px;
 background:#0b1428;min-height:75px
}
a{color:#80c8ff;font-weight:bold}
small{color:#a4b4d2}
</style>
</head>
<body>
<header>
<h1>🤖 NEXUS AI</h1>
<p>Local Autonomous Work Agent · Powered by Qwen3</p>
</header>
<main>
<section class="panel">
<h2>What should NEXUS AI do?</h2>
<p><small>Ask a question or create a 7-day Excel
study timetable using real AI tool execution.</small></p>
<textarea id="prompt">Create a 7-day Excel study
timetable for Python, Linux, Networking,
Cybersecurity.</textarea>
<button id="run" onclick="runTask()">Run Agent</button>
<div id="result">Ready for your first task.</div>
<div id="downloads"></div>
</section>
</main>
<script>
async function runTask(){
 const button=document.getElementById("run");
 const result=document.getElementById("result");
 const downloads=document.getElementById("downloads");
 button.disabled=true;
 result.textContent="NEXUS AI is working...";
 downloads.replaceChildren();
 try{
   const r=await fetch("/api/ask",{
     method:"POST",
     headers:{"Content-Type":"application/json"},
     body:JSON.stringify({
       prompt:document.getElementById("prompt").value
     })
   });
   const data=await r.json();
   if(!r.ok){
     throw new Error(data.detail || "Request failed");
   }
   result.textContent=data.answer;
   if(data.file_url){
     const link=document.createElement("a");
     link.href=data.file_url;
     link.textContent="⬇ Download generated Excel file";
     downloads.appendChild(link);
   }
 }catch(err){
   result.textContent="Error: "+err.message;
 }finally{
   button.disabled=false;
 }
}
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return HTMLResponse(PAGE)
