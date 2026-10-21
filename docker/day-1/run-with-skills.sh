#!/usr/bin/env bash
set -e

mkdir -p "$HOME/work/pytex-webinar/with-skills"
docker run -it --rm \
  -e MODE=with-skills \
  -e OPENCODE_API_KEY \
  -v "$HOME/work/pytex-webinar/with-skills:/workspace" \
  pytex-webinar:latest bash
