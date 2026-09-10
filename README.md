# SimplifyJobs Summer 2027 Discord Webhook

Posts newly added active Summer 2027 internships from `SimplifyJobs/Summer2027-Internships` to a Discord webhook.

The bot reads the repository's structured `.github/scripts/listings.json` dataset instead of scraping the rendered README.

## Local setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then set:

```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

Run:

```bash
python simplify_discord_webhook.py
```

## GitHub Actions hosting

This repository includes `.github/workflows/internships.yml`, which checks for new roles every 5 minutes.

Add your Discord webhook under GitHub repository settings as an Actions secret named:

```text
DISCORD_WEBHOOK_URL
```

The workflow runs the script once per invocation and commits `seen_jobs.json`, so subsequent runs only send newly added jobs.

By default, the first run records all existing Summer 2027 listings without flooding Discord.

## Optional environment variables

```env
POLL_SECONDS=300
MENTION=
SEND_EXISTING_ON_FIRST_RUN=false
STATE_FILE=seen_jobs.json
```

For a Discord role ping:

```env
MENTION=<@&ROLE_ID>
```

For `@everyone`:

```env
MENTION=@everyone
```
