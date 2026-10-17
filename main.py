
import os
import re
import json
import sqlite3
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from contextlib import closing

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="My Learning Assistant")

DB_PATH = os.getenv("MEMORY_DB", "memory.db")


def connect_db():
    return sqlite3.connect(DB_PATH, timeout=20)


def init_db():
    with closing(connect_db()) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE INDEX IF NOT EXISTS memory_question_index
            ON memory(question)
        """)
        db.commit()


init_db()


class Question(BaseModel):
    question: str


def normalize(text):
    return " ".join(text.casefold().split())


def search_wikipedia(question):
    url = (
        "https://en.wikipedia.org/w/api.php?"
        + urllib.parse.urlencode({
            "action": "query",
            "list": "search",
            "srsearch": question,
            "format": "json",
            "utf8": 1
        })
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "MyLearningAssistant/1.0 (learning project)"}
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))

        results = data.get("query", {}).get("search", [])
        if not results:
            return None, None

        item = results[0]
        title = item.get("title", "Wikipedia")
        snippet = item.get("snippet", "")

        # Remove HTML tags from Wikipedia search snippets.
        snippet = re.sub(r"<[^>]+>", "", snippet)
        snippet = (
            snippet.replace("&quot;", '"')
            .replace("&amp;", "&")
            .replace("&#039;", "'")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )

        source = (
            "https://en.wikipedia.org/wiki/"
            + urllib.parse.quote(title.replace(" ", "_"))
        )

        return f"{title}\n\n{snippet}", source

    except Exception:
        return None, None


def find_memory(question):
    key = normalize(question)

    with closing(connect_db()) as db:
        row = db.execute(
            """
            SELECT answer, source
            FROM memory
            WHERE question = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (key,)
        ).fetchone()

    return row


def save_memory(question, answer, source):
    with closing(connect_db()) as db:
        db.execute(
            """
            INSERT INTO memory(question, answer, source)
            VALUES (?, ?, ?)
            """,
            (normalize(question), answer, source)
        )
        db.commit()


@app.get("/", response_class=HTMLResponse)
def home():
    return """
<!doctype html>
<html lang="te">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Learning Assistant</title>
<style>
body {
  font-family: Arial, sans-serif;
  max-width: 720px;
  margin: 25px auto;
  padding: 16px;
  line-height: 1.6;
  background: #f5f7fb;
  color: #202735;
}
main {
  background: white;
  padding: 20px;
  border-radius: 14px;
}
textarea {
  width: 100%;
  box-sizing: border-box;
  min-height: 100px;
  padding: 12px;
  font-size: 16px;
}
button {
  padding: 12px 18px;
  margin-top: 10px;
  font-size: 16px;
  cursor: pointer;
}
#answer {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
a { overflow-wrap: anywhere; }
</style>
</head>
<body>
<main>
<h2>నా Learning Assistant</h2>
<p>మీ ప్రశ్నను తెలుగులో లేదా ఇంగ్లీషులో రాయండి.</p>
<textarea id="question" placeholder="మీ ప్రశ్న ఇక్కడ రాయండి"></textarea>
<br>
<button id="ask" onclick="askQuestion()">ప్రశ్న అడగండి</button>
<p id="status"></p>
<div id="answer"></div>
<p><a id="source" target="_blank" rel="noopener noreferrer"></a></p>
</main>
<script>
async function askQuestion() {
  const question = document.getElementById("question").value.trim();
  const status = document.getElementById("status");
  const answer = document.getElementById("answer");
  const source = document.getElementById("source");
  const button = document.getElementById("ask");

  if (!question) {
    status.textContent = "ముందుగా ప్రశ్న రాయండి.";
    return;
  }

  button.disabled = true;
  status.textContent = "సమాచారం వెతుకుతోంది...";
  answer.textContent = "";
  source.textContent = "";
  source.removeAttribute("href");

  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({question})
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "సర్వర్ లోపం");
    }

    answer.textContent = data.answer || "సమాధానం లేదు.";
    status.textContent = "స్థితి: " + data.status;

    if (data.source) {
      source.href = data.source;
      source.textContent = "సమాచార మూలాన్ని తెరవండి";
    }
  } catch (error) {
    status.textContent = "లోపం: " + error.message;
  } finally {
    button.disabled = false;
  }
}
</script>
</body>
</html>
"""


@app.post("/ask")
def ask(data: Question):
    question = data.question.strip()

    if not question:
        return {
            "answer": "దయచేసి ప్రశ్న రాయండి.",
            "source": None,
            "status": "EMPTY"
        }

    if len(question) > 1000:
        return {
            "answer": "ప్రశ్న 1000 అక్షరాల కంటే చిన్నదిగా ఉండాలి.",
            "source": None,
            "status": "TOO_LONG"
        }

    old = find_memory(question)

    if old:
        return {
            "answer": old[0],
            "source": old[1],
            "status": "MEMORY"
        }

    answer, source = search_wikipedia(question)

    if answer is None:
        return {
            "answer": (
                "వికీపీడియాలో సరిపడ సమాచారం దొరకలేదు. "
                "ప్రశ్నను మరో విధంగా అడిగి ప్రయత్నించండి."
            ),
            "source": None,
            "status": "NOT_FOUND"
        }

    save_memory(question, answer, source)

    return {
        "answer": answer,
        "source": source,
        "status": "WEB_SEARCH"
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "My Learning Assistant"}


@app.get("/memory/count")
def memory_count():
    with closing(connect_db()) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM memory"
        ).fetchone()[0]

    return {"saved_memories": count}
      
