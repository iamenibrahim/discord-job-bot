"""Send newly added SimplifyJobs Summer 2027 internships to Discord."""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

DEFAULT_LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/"
    "dev/.github/scripts/listings.json"
)
LISTINGS_URL = os.getenv("LISTINGS_URL", DEFAULT_LISTINGS_URL).strip()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "300"))
STATE_FILE = Path(os.getenv("STATE_FILE", "seen_jobs.json"))
SEND_EXISTING_ON_FIRST_RUN = os.getenv(
    "SEND_EXISTING_ON_FIRST_RUN", "false"
).lower() == "true"
MENTION = os.getenv("MENTION", "").strip()
RUN_ONCE = os.getenv("RUN_ONCE", "false").lower() == "true"
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
PREPARE_FILE = os.getenv("PREPARE_FILE", "").strip()
SEND_FILE = os.getenv("SEND_FILE", "").strip()
MAX_POST_AGE_DAYS = int(os.getenv("MAX_POST_AGE_DAYS", "14"))


def make_session():
    session = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=1,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({
        "User-Agent": "SimplifyJobs-Summer2027-Discord-Webhook/2.0",
        "Accept": "application/json",
    })
    return session


session = make_session()


def fetch_jobs():
    response = session.get(LISTINGS_URL, timeout=(10, 60))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("SimplifyJobs response was not a JSON list")

    jobs = []
    for job in data:
        if not isinstance(job, dict):
            continue
        terms = job.get("terms") or []
        if not job.get("active", False) or not job.get("is_visible", False):
            continue
        if not any("summer 2027" in str(term).lower() for term in terms):
            continue
        jobs.append(job)
    return jobs


def job_key(job):
    """Return the upstream ID, with a stable content fingerprint as fallback."""
    upstream_id = str(job.get("id") or "").strip()
    if upstream_id:
        return f"id:{upstream_id}"

    stable_fields = {
        "company": job.get("company_name") or "",
        "title": job.get("title") or "",
        "locations": sorted(job.get("locations") or []),
        "url": job.get("url") or job.get("company_url") or "",
    }
    serialized = json.dumps(stable_fields, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def load_seen():
    if not STATE_FILE.exists():
        return None
    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise RuntimeError(
            f"Could not safely read {STATE_FILE}; refusing to resend listings"
        ) from error

    if isinstance(data, list):  # Backward compatible with the original format.
        return {
            value if value.startswith(("id:", "sha256:")) else f"id:{value}"
            for item in data
            if (value := str(item).strip())
        }
    if isinstance(data, dict) and isinstance(data.get("seen"), list):
        return {str(value) for value in data["seen"]}
    raise RuntimeError(f"Invalid state format in {STATE_FILE}")


def save_seen(seen):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    payload = {
        "version": 1,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "seen": sorted(seen),
    }
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temp_file.replace(STATE_FILE)


def save_json(path, payload):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file = destination.with_suffix(destination.suffix + ".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    temp_file.replace(destination)


def format_date(timestamp):
    try:
        date = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
        return date.strftime("%b %d, %Y")
    except (TypeError, ValueError, OSError):
        return "Unknown"


def is_recent(job, now=None):
    """Return whether a listing is recent enough to notify."""
    try:
        posted = float(job.get("date_posted"))
        if posted > 10_000_000_000:  # Accept millisecond timestamps too.
            posted /= 1000
    except (TypeError, ValueError):
        return False

    current = time.time() if now is None else now
    age_seconds = current - posted
    return -86400 <= age_seconds <= MAX_POST_AGE_DAYS * 86400


def trim(text, limit):
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def build_embed(job):
    company = job.get("company_name", "Unknown company")
    title = job.get("title", "Internship")
    locations = job.get("locations") or []
    location_text = ", ".join(map(str, locations)) if locations else "Not listed"
    apply_url = job.get("url") or job.get("company_url") or LISTINGS_URL
    return {
        "title": trim(f"{company} | {title}", 256),
        "url": apply_url,
        "description": f"**[Apply here]({apply_url})**",
        "fields": [
            {"name": "Location", "value": trim(location_text, 1024), "inline": False},
            {"name": "Posted", "value": format_date(job.get("date_posted")), "inline": True},
            {"name": "Source", "value": trim(job.get("source", "Simplify"), 1024), "inline": True},
        ],
        "footer": {"text": "SimplifyJobs Summer 2027 Internships"},
    }


def post_job(job):
    payload = {
        "username": "Summer 2027 Internship Alerts",
        "embeds": [build_embed(job)],
        "allowed_mentions": {"parse": []},
    }
    if MENTION:
        payload["content"] = MENTION
        if MENTION == "@everyone":
            payload["allowed_mentions"] = {"parse": ["everyone"]}
        elif MENTION.startswith("<@&"):
            payload["allowed_mentions"] = {"parse": ["roles"]}
        elif MENTION.startswith("<@"):
            payload["allowed_mentions"] = {"parse": ["users"]}

    while True:
        response = session.post(DISCORD_WEBHOOK_URL, json=payload, timeout=(10, 30))
        if response.status_code == 429:
            try:
                retry_after = float(response.json().get("retry_after", 1))
            except (TypeError, ValueError, requests.JSONDecodeError):
                retry_after = 1
            time.sleep(max(retry_after, 1))
            continue
        response.raise_for_status()
        return


def job_sort_key(job):
    return (
        job.get("date_posted") or 0,
        str(job.get("company_name") or "").lower(),
        str(job.get("title") or "").lower(),
    )


def run_once():
    jobs = fetch_jobs()
    jobs_by_key = {job_key(job): job for job in jobs}
    current_keys = set(jobs_by_key)
    seen = load_seen()

    if seen is None and not SEND_EXISTING_ON_FIRST_RUN:
        if not DRY_RUN:
            save_seen(current_keys)
        print(
            f"Initialized with {len(current_keys)} current Summer 2027 jobs. "
            "No existing jobs were posted."
        )
        return 0
    if seen is None:
        seen = set()

    new_jobs = [jobs_by_key[key] for key in current_keys - seen]
    new_jobs.sort(key=job_sort_key)
    print(f"Found {len(new_jobs)} new job(s)." if new_jobs else "No new jobs.")

    for job in new_jobs:
        if DRY_RUN:
            print(
                f"Would post: {job.get('company_name', 'Unknown')} | "
                f"{job.get('title', 'Internship')}"
            )
            continue
        post_job(job)
        seen.add(job_key(job))
        save_seen(seen)
        print(
            f"Posted: {job.get('company_name', 'Unknown')} | "
            f"{job.get('title', 'Internship')}"
        )
        time.sleep(1)

    if not DRY_RUN:
        seen.update(current_keys)
        save_seen(seen)
    return len(new_jobs)


def prepare_jobs():
    """Persist IDs first and write a separate batch for later delivery."""
    jobs = fetch_jobs()
    jobs_by_key = {job_key(job): job for job in jobs}
    current_keys = set(jobs_by_key)
    seen = load_seen()

    if seen is None and not SEND_EXISTING_ON_FIRST_RUN:
        new_jobs = []
        print(
            f"Initialized with {len(current_keys)} current Summer 2027 jobs. "
            "No existing jobs were queued."
        )
    else:
        seen = seen or set()
        discovered = [jobs_by_key[key] for key in current_keys - seen]
        new_jobs = [job for job in discovered if is_recent(job)]
        stale_count = len(discovered) - len(new_jobs)
        print(
            f"Discovered {len(discovered)} new job(s); queued {len(new_jobs)} "
            f"and skipped {stale_count} older than {MAX_POST_AGE_DAYS} days."
        )

    new_jobs.sort(key=job_sort_key)
    save_seen((seen or set()) | current_keys)
    save_json(PREPARE_FILE, new_jobs)
    return len(new_jobs)


def send_prepared_jobs():
    try:
        with Path(SEND_FILE).open("r", encoding="utf-8") as file:
            jobs = json.load(file)
    except (json.JSONDecodeError, OSError) as error:
        raise SystemExit(f"Could not read prepared jobs from {SEND_FILE}") from error
    if not isinstance(jobs, list):
        raise SystemExit(f"Invalid prepared jobs format in {SEND_FILE}")

    print(f"Sending {len(jobs)} prepared job(s).")
    for job in jobs:
        post_job(job)
        print(
            f"Posted: {job.get('company_name', 'Unknown')} | "
            f"{job.get('title', 'Internship')}"
        )
        time.sleep(1)
    return len(jobs)


def validate_config():
    if PREPARE_FILE and SEND_FILE:
        raise SystemExit("PREPARE_FILE and SEND_FILE cannot be used together")
    if MAX_POST_AGE_DAYS < 1:
        raise SystemExit("MAX_POST_AGE_DAYS must be at least 1")
    if POLL_SECONDS < 60 and not RUN_ONCE:
        raise SystemExit("POLL_SECONDS must be at least 60")
    if DRY_RUN or PREPARE_FILE:
        return
    parsed = urlparse(DISCORD_WEBHOOK_URL)
    valid_hosts = {"discord.com", "discordapp.com"}
    if (
        parsed.scheme != "https"
        or parsed.netloc not in valid_hosts
        or "/api/webhooks/" not in parsed.path
    ):
        raise SystemExit(
            "DISCORD_WEBHOOK_URL is missing or invalid. Copy .env.example to .env "
            "and paste your Discord webhook URL."
        )


def main():
    validate_config()
    if PREPARE_FILE:
        prepare_jobs()
        return
    if SEND_FILE:
        send_prepared_jobs()
        return
    if RUN_ONCE:
        print("Checking SimplifyJobs Summer 2027 internships once.")
        run_once()
        return

    print(f"Watching every {POLL_SECONDS} seconds.")
    while True:
        try:
            run_once()
        except requests.RequestException as error:
            print(f"Network error: {error}")
        except RuntimeError as error:
            raise SystemExit(str(error)) from error
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
