#!/usr/bin/env bash
# Render build script for the Orionmano backend.
#
# Render's Python native runtime mounts the root filesystem read-only, so we
# can't `apt-get install` system packages. Workarounds:
#   - pandoc: use `pypandoc_binary` (PyPI wheel that bundles the pandoc
#     binary) — already in requirements.txt.
#   - libreoffice: there is no PyPI equivalent. Headless xlsx recalc is
#     SKIPPED on Render. The workpaper still ships, but the .summary.json
#     overlay uses Python-computed values instead of LibreOffice-recalc'd
#     cell values — analyst will see ~1-2% drift between dashboard and the
#     xlsx workbook. Acceptable for now; switch to Docker if Eric needs
#     exact-match parity.
set -euxo pipefail

pip install --upgrade pip
pip install -r requirements.txt
