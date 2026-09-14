# Network Debugger AI Frontend

React + Vite frontend for the Network Debugger Agent.

## Run locally

```bash
cd app/frontend
npm install
copy .env.example .env
npm run dev
```

For PowerShell, use `Copy-Item .env.example .env` instead of `copy` if needed.

Set `VITE_API_URL` to the FastAPI backend URL. The frontend uses the existing `/auth/login`, `/auth/signup`, `/auth/me`, and `/` diagnostic endpoints.

The current backend accepts only `query`, so the selected mode and investigation context are safely included in the diagnostic query until the API is extended with typed `mode`/`context` fields.

## Supabase

Authentication and user data remain controlled by the existing FastAPI + Supabase backend. Do not put a Supabase service-role key in this frontend. `VITE_SUPABASE_ANON_KEY` is only appropriate for browser-safe Supabase operations protected by RLS.

## Features

- Supabase-backed authentication through the existing FastAPI auth routes
- ChatGPT-style investigation workspace
- Network Debugger, Quick Diagnosis, Deep Investigation, Security Analysis and Incident Analysis modes
- Target/environment/live-diagnostics/knowledge-base context controls
- Agent diagnostic result cards
- Responsive mobile drawer
- Safe client-side conversation sharing via clipboard (no access token included)
