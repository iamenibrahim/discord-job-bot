# SimplifyJobs Summer 2027 Discord Webhook

Posts newly added, active Summer 2027 internships from
`SimplifyJobs/Summer2027-Internships` to a Discord webhook. It reads Simplify's
structured JSON dataset instead of scraping the rendered README.

## Fix the `dotenv` import error

`ModuleNotFoundError: No module named 'dotenv'` means the dependencies were not
installed in the Python environment running the script. From this directory:

```bash
py -m pip install -r requirements.txt
py simplify_discord_webhook.py
```

On macOS or Linux, replace `py` with `python3`. In VS Code, select the same
interpreter where the install command placed the packages.

## Local setup

Copy `.env.example` to `.env`, then replace the example webhook value. The real
`.env` is ignored by Git. Never paste a webhook into source, commits, issues, or
pull requests. If one is exposed, delete it in Discord and create a new one.

Safe verification that never contacts Discord:

```bash
DRY_RUN=true RUN_ONCE=true python3 simplify_discord_webhook.py
```

PowerShell:

```powershell
$env:DRY_RUN="true"
$env:RUN_ONCE="true"
py simplify_discord_webhook.py
```

## Free hosting with GitHub Actions

For this public repository, the included scheduled workflow is a free host. No
server needs to stay running.

1. Open **Settings > Secrets and variables > Actions** in this repository.
2. Choose **New repository secret**.
3. Name it `DISCORD_WEBHOOK_URL` and paste the webhook URL as its value.
4. Open **Actions > Internship Alerts** and enable workflows if GitHub asks.
5. Run the workflow manually once. It records current listings without sending
   old jobs. Future runs alert only on newly discovered listings.

The workflow checks every five minutes, although GitHub may delay scheduled runs
during busy periods. Before contacting Discord, it commits `seen_jobs.json` so
deduplication survives fresh runners. If that commit or push fails, it sends
nothing. This prevents a failed state save from causing duplicate alerts later.
Listings posted more than 14 days ago are recorded as seen but are not sent.

Do not set `SEND_EXISTING_ON_FIRST_RUN=true` unless you intentionally want every
current listing sent.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DISCORD_WEBHOOK_URL` | none | Required except in dry-run mode |
| `POLL_SECONDS` | `300` | Delay for continuous local hosting |
| `SEND_EXISTING_ON_FIRST_RUN` | `false` | Send the initial backlog |
| `STATE_FILE` | `seen_jobs.json` | Persistent deduplication state |
| `MENTION` | empty | Optional `@everyone`, user, or role mention |
| `RUN_ONCE` | `false` | Perform one check and exit |
| `DRY_RUN` | `false` | Print without Discord or state changes |
| `LISTINGS_URL` | SimplifyJobs JSON URL | Override the upstream source |
| `MAX_POST_AGE_DAYS` | `14` | Ignore listings older than this |

## Tests

```bash
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

Tests mock all network and Discord behavior. They send no messages.
