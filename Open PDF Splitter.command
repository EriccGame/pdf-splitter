#!/bin/bash
# Double-click to open PDF Splitter / Doble clic para abrir PDF Splitter
cd "$(dirname "$0")"
python3 -c "import pypdf" 2>/dev/null || pip3 install --user -r requirements.txt
python3 pdf_splitter.py
