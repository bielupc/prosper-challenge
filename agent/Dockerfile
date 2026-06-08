FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY agent/ ./agent/

# Run the WebRTC voice bot (7860) in the background and the WebSocket text server
# (7861, used by simulations) in the foreground so the container stays alive.
CMD ["sh", "-c", "uv run agent/bot.py --host 0.0.0.0 & exec uv run agent/ws_server.py"]
