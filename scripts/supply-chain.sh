#!/usr/bin/env bash
set -euo pipefail
mkdir -p artifacts
python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Run vulnerability scanning with Python 3.12"'
poetry check --lock
poetry export --only main --format requirements.txt --output artifacts/requirements.txt
pip-audit --progress-spinner off --no-deps --disable-pip \
  -r artifacts/requirements.txt --format json --output artifacts/python-audit.json
printf 'PASS locked Python dependency vulnerability scan\n'
if [[ $# -ne 1 ]]; then
  printf 'Supply the built image name for container scanning and SBOM generation.\n' >&2
  exit 2
fi
trivy image --format cyclonedx --output artifacts/sbom.cdx.json "$1"
printf 'PASS image SBOM generation\n'
trivy image --severity HIGH,CRITICAL --exit-code 1 --format json \
  --output artifacts/container-audit.json "$1"
printf 'PASS container vulnerability scan\n3/3 supply-chain checks passed\n'
