# Vercel runtime fix

The previous repository had both:

- `backend/app.py`
- `backend/app/` (Python package)

The wrapper `backend/app.py` imported `from app.main import app`.

When Vercel loads `app.py` as the Python function module, this creates a module/package
name collision around `app`, which can crash before FastAPI serves `/healthz`.

This version removes `backend/app.py` completely and uses the real FastAPI application:

- file: `backend/app/main.py`
- object: `app`
- pyproject entrypoint: `app.main:app`
- Vercel function config: `app/main.py`

No business logic, DeepSeek configuration, Source_B, Hero, chat, or frontend code was changed.
