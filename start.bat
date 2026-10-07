@echo off
rem Starts the backend (8000) and frontend (5173) in their own windows, then opens the app.
rem Close the two windows (or press Ctrl+C in each) to stop the app.

start "Backend" /D "%~dp0backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "Frontend" /D "%~dp0frontend" cmd /k "npm run dev"

timeout /t 6 /nobreak >nul
start "" http://localhost:5173
