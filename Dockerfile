# The web app with Audiveris. Build and run locally:
#   docker build -t readablemusic . && docker run --rm -p 8000:8000 readablemusic
FROM ubuntu:24.04

ARG AUDIVERIS_VERSION=5.11.0
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl fontconfig fonts-dejavu-core \
 && curl -fsSL -o /tmp/audiveris.deb "https://github.com/Audiveris/audiveris/releases/download/${AUDIVERIS_VERSION}/Audiveris-${AUDIVERIS_VERSION}-ubuntu24.04-x86_64.deb" \
 && mkdir -p /usr/share/applications /usr/share/desktop-directories /usr/share/mime/packages /usr/share/icons/hicolor \
 && apt-get install -y --no-install-recommends /tmp/audiveris.deb \
 && rm /tmp/audiveris.deb \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir /opt/tessdata \
 && for lang in eng heb; do \
      curl -fsSL -o /opt/tessdata/$lang.traineddata https://github.com/tesseract-ocr/tessdata/raw/main/$lang.traineddata; \
    done

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev

RUN useradd --create-home app && mkdir /data && chown app /data
USER app
# 3 GB for Java leaves room for Python within 4 GB; a 23-page score peaks at 3.0 to 3.6 GB.
ENV HOST=0.0.0.0 PORT=8000 READABLEMUSIC_DATA=/data TESSDATA_PREFIX=/opt/tessdata JAVA_TOOL_OPTIONS=-Xmx3g
# Without this, Audiveris loads GTK at startup just to read the screen scale, even in batch mode.
ENV GDK_SCALE=1
EXPOSE 8000
CMD ["/app/.venv/bin/readablemusic-web"]
