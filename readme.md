# Physics Job Hunter — Simple Guide

## What this project does

It automatically searches the web for physics teacher job postings, scores how well they match your profile, and sends you a notification about the best ones.

---

## Running it by hand

- **Run the job search now** — `python3 -m src.main`
  - Opens the program, searches for jobs, and shows the results right away.

---

## Running it on autopilot

- **Start the daily checker** — `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &`
  - Turns on a background robot that wakes up at specific times every day to look for jobs. Closing your computer won't turn it off.

- **Stop the robot** — `kill <PID>` (find with `ps aux | grep daily_run`)
  - Finds the running background robot and turns it off when you don't want it anymore.

- **Read the robot's diary** — `cat /tmp/scheduler.log`
  - Shows a plain-text report of what the robot found, when it ran, and whether anything went wrong.

---

## The Windows equivalents (PowerShell)

Same three ideas — find the robot, stop it, read its diary — but the words are slightly different because Windows speaks a different command language. If you are on Windows with WSL, adding `wsl` in front lets you use the simpler Linux commands instead.
