import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

LISTINGS_URL = (
    "https://raw.githubusercontent.com/"
    "SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json"
)

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))
STATE_FILE = Path(os.getenv("STATE_FILE", "seen_jobs.json"))
SEND_EXISTING_ON_FIRST_RUN = (
    os.getenv("SEND_EXISTING_ON_FIRST_RUN", "false").lower() == "true"
)
MENTION = os.getenv("MENTION", "").strip()
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"

session = requests.Session()
session.headers.update(
    {
        "User-Agent": "SimplifyJobs-Summer2027-Discord-Webhook/1.0",
        "Accept": "application/json",
    }
)


def fetch_jobs():
    response = session.get(LISTINGS_URL, timeout=30)
    response.raise_for_status()
    data = response.json()

    jobs = []
    for job in data:
        terms = job.get("terms", [])

        if not job.get("active", False):
            continue
        if not job.get("is_visible", False):
            continue
        if not any("Summer 2027" in term for term in terms):
            continue

        jobs.append(job)

    return jobs


def load_seen():
    if not STATE_FILE.exists():
        return None

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return set(data)
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen):
    temp_file = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(sorted(seen), file, indent=2)
    temp_file.replace(STATE_FILE)


def format_date(timestamp):
    try:
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return date.strftime("%b %d, %Y")
    except (TypeError, ValueError, OSError):
        return "Unknown"


def trim(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_embed(job):
    company = job.get("company_name", "Unknown company")
    title = job.get("title", "Internship")
    locations = job.get("locations", [])
    location_text = ", ".join(locations) if locations else "Not listed"
    apply_url = job.get("url") or job.get("company_url") or LISTINGS_URL
    source = job.get("source", "Simplify")
    posted = format_date(job.get("date_posted"))

    return {
        "title": trim(f"{company} | {title}", 256),
        "url": apply_url,
        "description": f"**[Apply here]({apply_url})**",
        "fields": [
            {
                "name": "Location",
                "value": trim(location_text, 1024),
                "inline": False,
            },
            {
                "name": "Posted",
                "value": posted,
                "inline": True,
            },
            {
                "name": "Source",
                "value": trim(source, 1024),
                "inline": True,
            },
        ],
        "footer": {
            "text": "SimplifyJobs Summer 2027 Internships"
        },
    }


def post_job(job):
    payload = {
        "username": "Summer 2027 Internship Alerts",
        "content": MENTION if MENTION else None,
        "embeds": [build_embed(job)],
        "allowed_mentions": {
            "parse": ["everyone", "roles", "users"] if MENTION else []
        },
    }

    if payload["content"] is None:
        del payload["content"]

    while True:
        response = session.post(DISCORD_WEBHOOK_URL, json=payload, timeout=30)

        if response.status_code == 429:
            try:
                retry_after = float(response.json().get("retry_after", 1))
            except Exception:
                retry_after = 1
            time.sleep(max(retry_after, 1))
            continue

        response.raise_for_status()
        return


def job_sort_key(job):
    return (
        job.get("date_posted", 0),
        job.get("company_name", "").lower(),
        job.get("title", "").lower(),
    )


def run_once():
    jobs = fetch_jobs()
    current_ids = {
        job["id"] for job in jobs if job.get("id")
    }

    seen = load_seen()

    if seen is None and not SEND_EXISTING_ON_FIRST_RUN:
        save_seen(current_ids)
        print(
            f"Initialized with {len(current_ids)} current Summer 2027 jobs. "
            "No existing jobs were posted."
        )
        return

    if seen is None:
        seen = set()

    new_jobs = [
        job
        for job in jobs
        if job.get("id") and job["id"] not in seen
    ]

    new_jobs.sort(key=job_sort_key)

    if not new_jobs:
        print(
            f"No new jobs. Tracking {len(current_ids)} active Summer 2027 jobs."
        )
    else:
        print(f"Found {len(new_jobs)} new job(s).")

    for job in new_jobs:
        post_job(job)
        seen.add(job["id"])
        save_seen(seen)
        print(
            f"Posted: {job.get('company_name', 'Unknown')} | "
            f"{job.get('title', 'Internship')}"
        )
        time.sleep(1)

    seen.update(current_ids)
    save_seen(seen)


def main():
    if not DISCORD_WEBHOOK_URL:
        raise SystemExit(
            "DISCORD_WEBHOOK_URL is missing. Copy .env.example to .env "
            "and paste your Discord webhook URL."
        )

    if RUN_ONCE:
        print("Checking SimplifyJobs Summer 2027 internships once.")
        run_once()
        return

    print(
        f"Watching SimplifyJobs Summer 2027 internships every "
        f"{POLL_SECONDS} seconds."
    )

    while True:
        try:
            run_once()
        except requests.RequestException as error:
            print(f"Network error: {error}")
        except Exception as error:
            print(f"Unexpected error: {error}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
