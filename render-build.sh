#!/usr/bin/env bash
# Render build script for the Orionmano backend.
#
# System packages:
#   - libreoffice-calc: headless xlsx recalc (Excel formula evaluation in
#     export_workpaper.py so the .summary.json overlay matches the workbook).
#   - pandoc: markdown → .docx conversion for the DRS Industry Section
#     deliverable (docx_export.py via pypandoc).
#   - fonts-liberation: Arial/Helvetica metric-compatible substitutes so
#     LibreOffice and pandoc produce visually correct output on a fontless
#     headless host.
#
# Python:
#   - pip install -r requirements.txt
set -euxo pipefail

apt-get update
apt-get install -y --no-install-recommends \
  libreoffice-calc \
  pandoc \
  fonts-liberation

pip install --upgrade pip
pip install -r requirements.txt
