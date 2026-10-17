# My Learning Assistant

A basic web search and memory application.

## Features

- No Gemini API key required
- Search Wikipedia
- Save answers in SQLite
- Reuse previously saved answers
- Simple mobile-friendly web page
- Health endpoint at /health

## Run locally

pip install -r requirements.txt

uvicorn main:app --host 0.0.0.0 --port 8000

## Important

This project is a basic search and memory application.
It is not a full AI language model.

For persistent memory on Render, configure a persistent
disk or external database and set MEMORY_DB to a path
on persistent storage.
