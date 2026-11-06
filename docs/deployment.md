# Deployment

The app runs on [Railway](https://railway.com) (Hobby plan) from the `Dockerfile`.
Railway rebuilds and redeploys on each push to the deployed branch. Deploying only what
is pushed also keeps the AGPL promise on the upload page: the source link shows what runs.

## Setting it up

1. Sign in at railway.com with GitHub and subscribe to Hobby. The Trial plan's 1 GB is
   too small: even a 2-page score peaks at 1.25 GB.
2. New Project, Deploy from GitHub repo, `amitrappel/ReadableMusic`. Railway finds the
   `Dockerfile` by itself.
3. In the service's Variables, add `PORT` = `8000`. Then in its Settings:
   - Source: choose the branch to deploy.
   - Networking: Generate Domain, target port 8000.
   - Deploy: health check path `/`. Leave Serverless off (see below).
   - Resource limits: memory 4 GB.
4. In the workspace's usage settings, set a hard limit of $10 (the lowest allowed). When
   usage reaches it, Railway takes the site offline instead of charging more.

## Sizing (measured in Docker with 2 CPUs and 4 GB)

| Pages | Time | Peak memory |
|---|---|---|
| 2 | 93 s | 1.25 GB |
| 4 | 189 s | 1.3 GB |
| 11 | 257 s | 1.5 GB |
| 15 | 784 s | 2.9 GB |
| 23 | 710 to 865 s | 3.0 to 3.6 GB |

Idle, the server uses about 100 MB. With 2 GB, the 23-page score runs out of memory.
At Railway's prices (2026-11) a page costs at most about $0.0015 and idling about
$1.30 a month, so the $5 included in Hobby covers roughly 2,000 pages a month.

## Decisions taken after research

- **Railway**: bills actual use, which suits a server that idles at 100 MB and works in
  bursts. Hugging Face Docker Spaces now need PRO ($9) and sleep when idle. Fly.io's shared
  CPUs are throttled to 6.25% once their burst balance runs out, and a dedicated 4 GB
  machine costs $66 a month. A Hetzner server with 2 vCPUs and 4 GB costs €19.99 and needs
  upkeep. Google Cloud Run may be free at low use, but it needs a storage bucket for results
  and has no hard spending limit.
- **Serverless stays off.** Railway sleeps a service 5 to 10 minutes after its last outbound
  traffic, which could stop a job whose user closed the tab.
- **No volume.** Jobs live on the container's disk, so a restart or redeploy loses results
  and running jobs. This is acceptable for now since results only last 24 hours anyway.
- **No `railway.toml`.** Railway retires that format on 2026-12-01, and it finds the
  `Dockerfile` without one.

## Abuse protection

Set in `src/readablemusic/web/__init__.py`:

- 50 MB per upload, refused before the body is parsed, and 30 pages per job.
- 5 jobs queued or running, and 10 jobs an hour from one address (`X-Real-IP`, which
  Railway's edge overwrites).
- Each job runs in its own process, so running out of memory costs that job only.
- PDF pages are rendered at 100 megapixels at most, whatever size they declare.
- Inputs are deleted when a job succeeds, and everything else after 24 hours.

There is no CAPTCHA yet. Add one if the limits above turn out not to be enough.
