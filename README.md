# ReadableMusic

A free, open-source web app that turns a poorly scanned sheet of a cappella
music (image or PDF) into a clean **MusicXML** file and an engraved **PDF**,
including Hebrew and English lyrics. Users can fix the recognised lyrics in
the browser before downloading.

Status: early development. See [docs/PLAN.md](docs/PLAN.md).

## Development

The project is managed with [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run python scripts/fetch_tools.py      # Windows: Audiveris + OCR data into tools/
uv run readablemusic score.pdf -o out/    # writes out/score.musicxml and out/score.pdf
uv run readablemusic-web                  # web app at http://127.0.0.1:8000
uv run python eval/samples.py             # every file in samples/raw -> work/samples/
uv run pytest
```

With an Anthropic API key, Claude checks the clefs, key and time signature of the first
system and reads the credits of scans (about 5 cents a score; see
`src/readablemusic/vision.py`), and on scans reads every system again with Audiveris's
reading as a draft, lyrics and chord symbols included (about 7 cents a system; `reader.py`). Put `ANTHROPIC_API_KEY=...` in a `.env` file, which git
ignores, and add `--env-file .env` after `uv run`. Without a key this step is skipped.

## Deployment

The `Dockerfile` holds everything the web app needs. See
[docs/deployment.md](docs/deployment.md).

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
