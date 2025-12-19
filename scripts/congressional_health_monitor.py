"""
Background health monitor for congressional scraper workers.
- Runs health checks every 90 seconds
- Provides full status every 5 minutes
- Auto-restarts stalled workers
- Logs everything to file

Usage: python scripts/congressional_health_monitor.py
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CHECK_INTERVAL = 90  # 1.5 minutes
STATUS_EVERY_N_CHECKS = 4  # Full status every 4 checks (~5 mins)
LOG_FILE = Path("D:/AI/logs/congressional_scraper/health_monitor.log")


def log(msg: str, also_print: bool = True):
    """Log to file and optionally print."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    if also_print:
        print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_command(cmd: str):
    """Run supervisor command."""
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    result = subprocess.run(
        [sys.executable, "-m", "api_gateway.services.congressional_parallel_supervisor", cmd],
        capture_output=True,
        text=True,
        cwd="D:/AI",
        creationflags=creationflags,
    )
    return result.stdout, result.stderr, result.returncode


def log_separator():
    sep = "=" * 60
    log(sep)


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    log_separator()
    log("Congressional Health Monitor STARTED")
    log(
        f"Health check: every {CHECK_INTERVAL}s | Full status: every {CHECK_INTERVAL * STATUS_EVERY_N_CHECKS}s"
    )
    log(f"Log file: {LOG_FILE}")
    log_separator()

    check_count = 0

    while True:
        try:
            check_count += 1

            # Run health check
            stdout, stderr, code = run_command("check")

            # Determine if any action was taken
            actions = []
            for line in stdout.split("\n"):
                line_lower = line.lower()
                if any(x in line_lower for x in ["restart", "kill", "stale", "crashed", "action"]):
                    actions.append(line.strip())

            # Full status every N checks
            if check_count % STATUS_EVERY_N_CHECKS == 0:
                log_separator()
                log("STATUS UPDATE")
                status_out, _, _ = run_command("status")
                for line in status_out.strip().split("\n"):
                    log(f"  {line}")
                if actions:
                    log("Actions taken this cycle:")
                    for a in actions:
                        log(f"  - {a}")
                log_separator()
            else:
                # Brief check output
                if actions:
                    log(f"ACTIONS: {'; '.join(actions)}")
                elif stderr:
                    log(f"ERROR: {stderr[:100]}")
                else:
                    log(f"OK - check #{check_count}")

        except KeyboardInterrupt:
            log("Monitor stopped by user")
            break
        except Exception as e:
            log(f"Monitor error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
