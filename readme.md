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

The robot wakes up at 06:00, 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, and 22:00 every day.

---

## If systemd is not available (fallback)

- **Start the background robot** — `nohup python3 -c "from src.scheduler.daily_run import start; start()" > /tmp/scheduler.log 2>&1 &`
  - This one **dies on reboot**. It's only useful if systemd isn't available.

- **Stop the robot** — `kill <PID>` (find with `ps aux | grep daily_run`)

- **Read the robot's diary** — `cat /tmp/scheduler.log`
