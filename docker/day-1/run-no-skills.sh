#!/usr/bin/env bash
set -e

mkdir -p "$HOME/work/pytex-webinar/no-skills"
docker run -it --rm \
  -e MODE=no-skills \
  -e OPENCODE_API_KEY \
  -v "$HOME/work/pytex-webinar/no-skills:/workspace" \
  pytex-webinar:latest bash
