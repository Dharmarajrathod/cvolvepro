# CvolvePro

An AI career search workspace that discovers roles across public job boards and company career pages using NVIDIA NIM. Results are source-linked, normalized, deduplicated, and ranked against the candidate's skills.

## Run locally

1. Copy `.env.example` to `.env` and add `NVIDIA_API_KEY` from NVIDIA Build. The default model is `nvidia/nemotron-3-super-120b-a12b`; set `NVIDIA_MODEL` to another NVIDIA-hosted or NVIDIA-compatible chat model if needed.
   Email verification uses SMTP. Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_USE_SSL` when the defaults for `no-reply@cvolvepro.com` need to change.
   Stripe Checkout uses `STRIPE_SECRET_KEY` on the backend and `STRIPE_PUBLISHABLE_KEY` for public configuration. Use real Stripe keys from the Stripe dashboard, usually starting with `sk_` and `pk_`.
2. Start the API:
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
3. Start the web app:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. Open http://localhost:3000.

For PostgreSQL, set `DATABASE_URL=postgresql+asyncpg://user:pass@host/db`. Search requests require a real NVIDIA API key; the app intentionally has no sample or fabricated jobs.

## Production

Build with `docker compose up --build`, or deploy `frontend` to Vercel and `backend` to Railway/Render. Set `NEXT_PUBLIC_API_URL` to the public backend URL and set `ALLOWED_ORIGINS` to the deployed frontend origins, for example `https://cvolvepro.com,https://www.cvolvepro.com`.

Pricing is selected from the visitor IP country on the backend. India (`IN`) receives INR pricing; all other country codes receive international USD pricing. Make sure the hosting proxy forwards a country header such as `cf-ipcountry`, `x-vercel-ip-country`, `x-country-code`, or `x-forwarded-country`.
