# Deployment

The app runs on [Railway](https://railway.com) (Hobby plan) from the `Dockerfile`, at
https://readablemusic-production.up.railway.app. Railway rebuilds and redeploys on each
push to `master`, and a redeploy loses running jobs and results (see below). Deploying
only what is pushed also keeps the AGPL promise on the upload page: the source link shows
what runs.

## Setting it up

1. Sign in at railway.com with GitHub and subscribe to Hobby. The Trial plan's 1 GB is
   too small: even a 2-page score peaks at 1.25 GB.
2. New Project, Deploy from GitHub repo, `amitrappel/ReadableMusic`. Railway finds the
   `Dockerfile` by itself.
3. In the service's Variables, add `PORT` = `8000`. Then in its Settings:
   - Source: branch `master`.
   - Networking: Generate Domain, target port 8000.
   - Deploy: health check path `/`. Leave Serverless off (see below).
   - Resource limits: memory 4 GB.
4. In the workspace's usage settings, set a hard limit of $10 (the lowest allowed). When
   usage reaches it, Railway takes the site offline instead of charging more.

The image also needs everything the code loads at run time. OCR data is downloaded into
`/opt/tessdata` (`eng` and `heb`). Without `heb`, the credits reader skips Hebrew instead
of failing, so a missing download shows only as worse results.

## Running it on Railway

- **Address:** the service's Settings, Networking, Public Networking.
- **Deploys:** each push to `master` rebuilds and redeploys. The site switched over 73 s
  after a push that changed no dependencies.
- **Restart** (clears jobs, results and the hourly counts): open the service's Deployments,
  open the active deployment and press Ctrl+K, then choose restart. Railway shows a Restart
  button only on crashed deployments. Redeploy, in the deployment's ⋯ menu, also works.
- **Memory and cost:** the service's metrics and the workspace's usage page. Memory on
  Railway has not been checked against the sizing table yet.

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

Checked on Railway (2026-11-07): a 2-page score converted in 100 s and a lyric edit saved;
oversized, unreadable, too long and unsized uploads were refused; the 11th job in an hour
was refused even with a different forged `X-Real-IP` on each upload. The count is kept in
memory, so restarting the service clears it.

## Testing the image

```
docker build -t readablemusic .
docker run --rm --cpus=2 --memory=4g -p 8000:8000 readablemusic    # Railway's limits
scripts/try_server.sh http://127.0.0.1:8000 score.pdf out/          # or the Railway address
uv run python -X utf8 scripts/compare_scores.py a.musicxml b.musicxml
scripts/measure_docker.sh readablemusic 2 4g score.pdf ...           # time and memory
```

In Git Bash, `docker` needs `MSYS_NO_PATHCONV=1` for paths inside the container, such as
`/sys/fs/cgroup`, but `curl` must not get it, or it cannot find local files.
`measure_docker.sh` sets it for `docker` only. `.gitattributes` keeps `.sh` files in Unix
line endings on checkout: with `core.autocrlf` on, Git on Windows would otherwise give them
Windows line endings, and Bash fails on those with `$'\r': command not found`.

Checked after the merge with round 5 (2026-11-07), against Windows results:

- Irish Blessing matched current `master` on Windows, except that the image kept the last
  lyric line ("hand. May God hold in the palm of His hand."), which Windows missed.
- Siyahamba matched an earlier Windows result exactly.
- ניגע אל החלום (3 pages) matched an earlier Windows result in notes, title and Hebrew
  credits (repaired from the page), with one more lyric syllable. Current `master` on
  Windows crashed on it (see Open items). On Railway it took 110 s and matched the local
  image exactly.

The three samples together peaked at 1.5 GB.

## Open items

- Delete the `hosting` branch on GitHub. It was merged into `master` and Railway no longer
  uses it; Claude Code's permission check blocked deleting it.
- A blank page fails with the generic "Recognition failed": `_otsu` in `scale.py` raises
  "All-NaN slice" on an image with a single gray level. Real scans do not hit this.
- On Windows, `uv run readablemusic` crashes after recognition when its output is
  redirected and the credits hold Hebrew: printing them (`pipeline.py`, "Text on the
  page") fails in the console's cp1252. Nothing is written. Set `PYTHONUTF8=1` until fixed.
- No CAPTCHA, and no volume: see above.
