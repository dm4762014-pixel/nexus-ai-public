from pathlib import Path
from threading import Lock
from typing import Literal
import re

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel, Field
from ollama import chat

from webapp import create_study_timetable
from document_tools import create_report
from research_tools_v31 import research_web

app = FastAPI(title="NEXUS AI v2")
MODEL = "qwen3:1.7b"
OUTPUT = Path(__file__).parent / "outputs"
lock = Lock()


class Request(BaseModel):
    prompt: str = Field(min_length=1, max_length=500)
    mode: Literal["chat", "excel", "pdf", "docx", "both", "research"]


def ask_model(messages, tools=None, tokens=600):
    kwargs = {
        "model": MODEL,
        "messages": messages,
        "think": False,
        "options": {
            "num_ctx": 2048,
            "num_predict": tokens
        },
        "keep_alive": "30s"
    }
    if tools:
        kwargs["tools"] = tools
    return chat(**kwargs)


@app.post("/api/task")
def run_task(request: Request):
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "Another task is running")

    try:
        if request.mode == "research":
            return research_web(request.prompt)

        if request.mode == "excel":
            result = ask_model(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are NEXUS AI. The user wants "
                            "a seven-day Excel timetable. "
                            "Call create_study_timetable with "
                            "comma-separated subject names. "
                            "Do not invent successful tool results."
                        )
                    },
                    {"role": "user", "content": request.prompt}
                ],
                tools=[create_study_timetable],
                tokens=350
            )

            calls = result.message.tool_calls or []
            if len(calls) != 1:
                raise ValueError("AI did not select the Excel tool")

            call = calls[0]
            if call.function.name != "create_study_timetable":
                raise ValueError("Unapproved tool")

            subjects = call.function.arguments.get("subjects")
            if not isinstance(subjects, str):
                raise ValueError("Invalid subjects")

            file_id = create_study_timetable(subjects)

            return {
                "answer": "Excel timetable created and verified.",
                "files": [{
                    "name": "Study_Plan.xlsx",
                    "url": f"/api/download/{file_id}.xlsx"
                }]
            }

        if request.mode in ("pdf", "docx", "both"):
            response = ask_model(
                [
                    {
                        "role": "system",
                        "content": (
                            "Write a clear, short educational report "
                            "in simple English. Use short sections. "
                            "Do not invent statistics or claim to "
                            "have performed web research. "
                            "Output plain text only."
                        )
                    },
                    {"role": "user", "content": request.prompt}
                ],
                tokens=650
            )

            content = (response.message.content or "").strip()

            formats = (
                ["pdf", "docx"]
                if request.mode == "both"
                else [request.mode]
            )

            files = create_report(
                title="NEXUS AI Report",
                content=content,
                formats=formats
            )

            return {
                "answer": (
                    "Report files created and structurally verified. "
                    "The factual content has not been independently "
                    "checked against external sources."
                ),
                "files": files
            }

        response = ask_model([
            {
                "role": "system",
                "content": (
                    "You are NEXUS AI, a helpful local assistant. "
                    "Be clear and accurate. Do not claim you "
                    "performed actions without tools."
                )
            },
            {"role": "user", "content": request.prompt}
        ])

        return {
            "answer": response.message.content or "No response",
            "files": []
        }

    except Exception as error:
        print("NEXUS task failed:", repr(error))
        raise HTTPException(
            status_code=422,
            detail="Task failed. Check the PowerShell log."
        )
    finally:
        lock.release()


@app.get("/api/download/{filename}")
def download(filename: str):
    if not re.fullmatch(r"[a-f0-9]{32}\.(xlsx|pdf|docx)", filename):
        raise HTTPException(400, "Invalid filename")

    path = OUTPUT / filename
    if not path.is_file():
        raise HTTPException(404, "File not found")

    return FileResponse(path, filename="NEXUS_" + filename)


PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXUS AI v2</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#080d1d;color:#eff4ff;
font-family:Segoe UI,Arial,sans-serif}
header{background:#111b32;padding:25px;
border-bottom:1px solid #304367}
h1{margin:0;color:#8db5ff}
header p{color:#aab9d9}
main{max-width:850px;margin:40px auto;padding:15px}
.panel{background:#142039;border:1px solid #354c75;
border-radius:16px;padding:25px}
textarea,select{width:100%;background:#091326;
border:1px solid #425a82;color:white;
padding:14px;border-radius:9px;font-size:16px}
textarea{min-height:125px;resize:vertical;margin:15px 0}
button{background:#626df5;color:white;border:0;
border-radius:9px;padding:13px 25px;
font-size:16px;cursor:pointer}
button:disabled{opacity:.5}
#result{white-space:pre-wrap;margin-top:20px;
background:#0c1528;padding:18px;border-radius:10px;
line-height:1.6;overflow-wrap:anywhere}
#files a{display:block;color:#83ceff;
margin-top:14px}
small{color:#aab9d9}
</style>
</head>
<body>
<header>
<h1>ðŸ¤– NEXUS AI</h1>
<p>Local AI Work Agent Â· Qwen3 Â· Windows</p>
</header>
<main>
<div class="panel">
<h2>What should NEXUS AI do?</h2>
<label for="mode">Select a task</label>
<select id="mode">
<option value="chat">AI Chat</option>
<option value="research">Live Web Research</option>
<option value="excel">Create Excel timetable</option>
<option value="pdf">Create PDF report</option>
<option value="docx">Create Word report</option>
<option value="both">Create PDF + Word</option>
</select>
<textarea id="prompt"
placeholder="Describe your task..."></textarea>
<button id="run" onclick="runTask()">Run Agent</button>
<div id="result">Ready for a new task.</div>
<div id="files"></div>
<p><small>Live Web Research is available. PDF and Word modes do not yet use research sources.
Do not expose this dashboard publicly.</small></p>
</div>
</main>
<script>
async function runTask(){
 const btn=document.getElementById("run");
 const result=document.getElementById("result");
 const files=document.getElementById("files");

 btn.disabled=true;
 result.textContent="NEXUS AI is working...";
 files.replaceChildren();

 try{
  const response=await fetch("/api/task",{
   method:"POST",
   headers:{"Content-Type":"application/json"},
   body:JSON.stringify({
    prompt:document.getElementById("prompt").value,
    mode:document.getElementById("mode").value
   })
  });

  const data=await response.json();
  if(!response.ok){
   throw new Error(data.detail || "Task failed");
  }

  result.textContent=data.answer;
  for(const source of data.sources || []){
   const a=document.createElement("a");
   a.href=source.url;
   a.target="_blank";
   a.rel="noopener noreferrer";
   a.textContent="["+source.number+"] "+source.title;
   files.appendChild(a);
  }
  for(const file of data.files || []){
   const a=document.createElement("a");
   a.href=file.url;
   a.textContent="â¬‡ Download "+file.name;
   files.appendChild(a);
  }
 }catch(error){
  result.textContent="Error: "+error.message;
 }finally{
  btn.disabled=false;
 }
}
</script>
</body>
</html>
"""


@app.get("/")
def home():
    return HTMLResponse(PAGE)



