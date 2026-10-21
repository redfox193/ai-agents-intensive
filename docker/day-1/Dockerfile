# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies: PostgreSQL, git, build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    python3-dev \
    libpq-dev \
    postgresql \
    postgresql-contrib \
    sqlite3 \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install OpenCode CLI
RUN test "$(uname -m)" = "aarch64" \
    && curl -fsSL --compressed https://github.com/anomalyco/opencode/releases/download/v1.19.0/opencode-linux-arm64.tar.gz -o /tmp/opencode.tar.gz \
    || curl -fsSL --compressed https://github.com/anomalyco/opencode/releases/download/v1.19.0/opencode-linux-x64.tar.gz -o /tmp/opencode.tar.gz \
    && tar -xzf /tmp/opencode.tar.gz -C /usr/local/bin \
    && rm -f /tmp/opencode.tar.gz \
    && chmod +x /usr/local/bin/opencode

# Git identity for workshop
RUN git config --global user.name "Pytex Student" \
    && git config --global user.email "student@pytex.local"

# Configure OpenCode global authentication with active key
ARG OPENCODE_API_KEY=""
ENV OPENCODE_API_KEY=${OPENCODE_API_KEY}
ENV OPENCODE_PURE=1
ENV OPENCODE_DISABLE_CLAUDE_CODE=1
ENV OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1

RUN mkdir -p /root/.config/opencode \
    && printf '{"$schema":"https://opencode.ai/config.json","model":"opencode-go/glm-5.3-flash","permission":"allow"}' > /root/.config/opencode/opencode.json

# Copy project template and pre-build virtual environment
WORKDIR /opt/fastapi-template
COPY fastapi /opt/fastapi-template
RUN uv sync --frozen \
    && cp -r .venv /opt/base-venv

# Setup entrypoint
WORKDIR /workspace
COPY docker/day-1/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["bash"]
