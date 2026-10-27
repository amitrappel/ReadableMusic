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
uv run pytest
```

## License

AGPL-3.0-or-later. See [LICENSE](LICENSE).
