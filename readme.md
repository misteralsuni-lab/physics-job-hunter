# Physics Job Hunter — Simple Guide

## What this project does

It automatically searches the web for physics teacher job postings, scores how well they match your profile, and sends you a notification about the best ones.

---

## Running it by hand

- **Run the job search now** — `cd /mnt/d/physics-job-hunter && python3 -m src.main`
  - Opens the program, searches for jobs, and shows the results right away.

---

## Running it on autopilot (systemd)

The scheduler runs as a background service managed by systemd. It auto-starts on power-on, restarts itself if it crashes, and survives sleep, hibernation, and reboots.

- **Turn it on now** — `systemctl --user start physics-job-hunter.service`
- **Turn it off** — `systemctl --user stop physics-job-hunter.service`
- **Check if it's running** — `systemctl --user status physics-job-hunter.service`
- **Watch live activity** — `journalctl --user -u physics-job-hunter.service -f`
- **Stop it from auto-starting on boot** — `systemctl --user disable physics-job-hunter.service`

The robot wakes up at the times set in `SCHEDULE_TIME` (default `08:00, 17:00, 22:00, 22:30, 23:00`) every day.

---

## Tutoring leads (inbound bot)

A separate Telegram bot answers tutoring enquiries and captures leads into the same dashboard.

- **Turn it on** — `systemctl --user start physics-job-hunter-bot.service`
- **Turn it off** — `systemctl --user stop physics-job-hunter-bot.service`
- **Watch live activity** — `journalctl --user -u physics-job-hunter-bot.service -f`

---

## Front-end dashboard (web/)

A touch-friendly Next.js control panel for the pipeline (dashboard, pipeline control, settings, and tutoring leads).

- **Install dependencies** — `cd web && pnpm install`
- **Run it while developing** — `cd web && pnpm dev` (opens at http://localhost:3000)
- **Check for errors before committing** — `cd web && pnpm typecheck && pnpm lint`
- **Build for production** — `cd web && pnpm build` (on low-memory machines: `NODE_OPTIONS="--max-old-space-size=2048" pnpm build`)
- **Run the production build** — `cd web && pnpm start`

The dashboard reads its settings from `web/.env.local` (Supabase URL + service-role key, `PIPELINE_CWD`, `SYSTEMD_UNIT`, optional `ADMIN_TOKEN`). See `web/README.md` for the full list.

---

## If systemd is not available (fallback)

- **Start the background robot** — `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &`
  - This one **dies on reboot**. It's only useful if systemd isn't available.

- **Stop the robot** — `kill <PID>` (find with `ps aux | grep daily_run`)

- **Read the robot's diary** — `cat /tmp/scheduler.log`
