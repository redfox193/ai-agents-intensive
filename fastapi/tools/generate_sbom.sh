#!/usr/bin/env bash
set -euo pipefail

echo "======================================================="
echo "   ГЕНЕРАЦИЯ ENTERPRISE SBOM (CycloneDX / SPDX)"
echo "======================================================="

uv run cyclonedx-py requirements requirements.txt --output-format json --output-file docs/compliance/sbom.cyclonedx.json

trivy sbom docs/compliance/sbom.cyclonedx.json --severity HIGH,CRITICAL

echo "SBOM успешно сформирован и проверен!"
