# My Project

Monorepo: ESP32 firmware + FastAPI backend + Flutter app

## Structure
- `firmware/` : ESP32 (Arduino). Copy `secrets.h.example` to `secrets.h`.
- `backend/`  : FastAPI (Python). Copy `.env.example` to `.env`.
- `app/`      : Flutter app.

## Firmware (ESP32)
- Board: ESP32 Dev Module
- Build & Upload in Arduino IDE.
- Configure Wi-Fi/URL in `firmware/secrets.h`.

## Backend (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U fastapi uvicorn pydantic
cp .env.example .env
uvicorn app.main:app --reload
