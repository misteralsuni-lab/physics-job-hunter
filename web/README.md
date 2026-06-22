# Physics Job Hunter — Front End

Reactive, touch-friendly dashboard for the Physics Job Hunter scraping and LLM-scoring pipeline. Built with **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, **Zustand** for state, and **@supabase/ssr** for server-side data access.

## Quick Start

```bash
cd web
cp .env.example .env.local   # fill in Supabase creds + optional ADMIN_TOKEN
npm install                  # or pnpm install
npm run dev                  # starts on http://localhost:3000
```

### Environment Variables (`web/.env.local`)

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Your Supabase project URL (e.g. `https://<ref>.supabase.co`). |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Service-role key for server-side reads. **Never exposed to the browser.** |
| `SUPABASE_ANON_KEY` | No | Public/anon key — currently unused; all reads go via server route handlers. |
| `PIPELINE_CWD` | No | Absolute path to the Python project root. Default: `/mnt/d/physics-job-hunter`. |
| `SYSTEMD_UNIT` | No | systemd user unit name. Default: `physics-job-hunter.service`. |
| `ADMIN_TOKEN` | No | Shared secret for mutating pipeline endpoints. If unset, mutating calls are restricted to `localhost` (`127.0.0.1` / `::1`). |
| `NOTIFY_SCORE_THRESHOLD` | No | Advisory notification threshold (mirrors Python `.env`). Default: `50`. |
| `SCHEDULE_TIME` | No | Comma-separated 24h schedule times (mirrors Python `.env`). Default: `08:00,17:00,22:00,22:30,23:00`. |

## Available Scripts

| Command | Purpose |
|---------|---------|
| `npm run dev` | Start development server with Turbopack. |
| `npm run build` | Production build (static + server). |
| `npm run start` | Run production build. |
| `npm run lint` | ESLint with Next.js config. |
| `npm run typecheck` | `tsc --noEmit` — strict type checking without emitting files. |

## Project Structure

```
web/
├── app/
│   ├── api/
│   │   ├── jobs/
│   │   │   ├── route.ts           # GET paginated, filtered jobs
│   │   │   └── options/route.ts   # GET distinct filter values (sources, countries)
│   │   ├── settings/route.ts      # GET/POST advisory settings (web/config.json)
│   │   └── pipeline/
│   │       ├── status/route.ts    # GET systemd service state
│   │       ├── start/route.ts     # POST start scheduler
│   │       ├── stop/route.ts      # POST stop scheduler
│   │       ├── run/route.ts       # POST manual pipeline run (detached)
│   │       └── logs/route.ts      # GET journalctl tail
│   ├── page.tsx                   # Dashboard (jobs table + filters)
│   ├── pipeline/page.tsx          # Pipeline Control (status, logs, actions)
│   ├── settings/page.tsx          # Settings (threshold, schedule times)
│   ├── layout.tsx                 # Root layout + Sidebar + Toast viewport
│   ├── globals.css                # Design tokens + base styles
│   ├── loading.tsx / error.tsx    # Route-level boundaries
│   └── components/
│       ├── layout/Sidebar.tsx     # Responsive nav (rail + mobile tab bar)
│       ├── ui/                    # Reusable touch-friendly primitives
│       │   ├── Button.tsx
│       │   ├── Card.tsx
│       │   ├── EmptyState.tsx
│       │   ├── NumberInput.tsx
│       │   ├── Pagination.tsx
│       │   ├── Slider.tsx
│       │   ├── Spinner.tsx
│       │   ├── StatusBadge.tsx
│       │   ├── Toggle.tsx
│       │   └── Toast.tsx
│       └── jobs/                  # Jobs-table specific components
│           ├── Chips.tsx
│           ├── JobDetailDrawer.tsx
│           ├── JobTable.tsx
│           ├── JobTableFilters.tsx
│           ├── JobTableSkeleton.tsx
│           ├── Pagination.tsx
│           └── ScoreBadge.tsx
├── lib/
│   ├── api/
│   │   ├── guards.ts              # Auth helper for mutating pipeline routes
│   │   └── settings-store.ts      # web/config.json read/write
│   ├── supabase/server.ts         # Server-only Supabase client (service role)
│   ├── store/
│   │   ├── jobs.ts                # Zustand store: jobs list, filters, sort, pagination
│   │   └── settings.ts            # Zustand store: advisory settings
│   ├── types/job.ts               # Shared TS interfaces (Job, JobListResponse, etc.)
│   └── utils/cn.ts                # clsx + tailwind-merge + British date helpers
├── .env.example
├── .gitignore
├── next.config.mjs
├── package.json
├── pnpm-workspace.yaml
├── postcss.config.js
├── tailwind.config.ts
└── tsconfig.json
```

## Routes

| Route | Description |
|-------|-------------|
| `/` | Dashboard — scored job listings with filters, sort, pagination, detail drawer. |
| `/pipeline` | Pipeline Control — systemd status, Start/Stop/Run buttons, live log viewer. |
| `/settings` | Settings — advisory notification threshold (0–100 slider + number input) and schedule times editor. |

## API Endpoints

### Jobs

| Method | Path | Query Params | Response |
|--------|------|--------------|----------|
| `GET` | `/api/jobs` | `page`, `pageSize`, `sort` (score\|created_at\|...), `dir` (asc\|asc/desc, `source`, `country`, `minScore`, `maxScore`, `notified`true/false, `q` (search) | `{ jobs, total, page, pageSize, error }` |
| `GET` | `/api/jobs/options` | — | `{ sources[], countries[], error }` |

### Settings (advisory, persisted to `web/config.json`)

| Method | Path | Body | Response |
|--------|------|------|----------|
| `GET` | `/api/settings` | — | `{ notifyScoreThreshold, scheduleTimes[] }` |
| `POST` | `/api/settings` | `{ notifyScoreThreshold: 0–100, scheduleTimes: ["HH:MM", ...] }` | Updated settings |

### Pipeline Control (mutating — require `x-admin-token` or localhost)

| Method | Path | Response |
|--------|------|----------|
| `GET` | `/api/pipeline/status` | `{ active, sub, status, lastStart, error }` |
| `POST` | `/api/pipeline/start` | `{ ok, message }` |
| `POST` | `/api/pipeline/stop` | `{ ok, message }` |
| `POST` | `/api/pipeline/run` | `202 { ok, runId, message }` (detached `python3 -m src.main`) |
| `GET` | `/api/pipeline/logs?lines=200` | `{ lines[], error }` |

**Security**: All mutating endpoints reject non-local requests unless `ADMIN_TOKEN` is set in the server env **and** the client sends it via `x-admin-token` header. On `localhost` without a token, access is allowed.

## Design System

- **Colours**: Semantic tokens in `tailwind.config.ts` (`surface`, `ink`, `line`, `brand`, `status`, `score`).
- **Typography**: British English throughout (standardise, programme, labelling, colour, etc.).
- **Touch targets**: Minimum 44×44 px via `.tap-target` utility and component internals.
- **Accessibility**: Focus rings, ARIA labels/roles, keyboard navigation, `prefers-reduced-motion` respected.
- **Dark mode**: Automatic via `prefers-color-scheme` media query.

## Development Notes

- The Supabase service-role key **never leaves the server** — it is used only in route handlers and server components.
- The `job_listings` table schema lives at `/scripts/setup_supabase.sql` in the repo root.
- The Python pipeline is triggered via `python3 -m src.main` (spawned detached from `/api/pipeline/run`).
- The systemd user service `physics-job-hunter.service` manages the scheduled runs (APScheduler).
- Advisory settings in the UI mirror the Python pipeline’s `.env`; they do not auto-apply to the scheduler.

## Building for Production

```bash
npm run build
npm run start
```

Deploy the `web/` directory to any Node.js host (Vercel, Docker, etc.). Ensure the server can reach Supabase and, if using the pipeline controls, has access to the Python project and `systemctl --user`.