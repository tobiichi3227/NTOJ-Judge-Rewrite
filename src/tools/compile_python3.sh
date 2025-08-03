#!/bin/bash
set -e

if [[ $# -ne 2 ]]; then
    echo "Usage: $0 <main_module_without_py> <output_pyz>"
    exit 1
fi

main_py="$1"
output_pyz="$2"

python3 -m compileall -q -o 2 -b . 1>&2

if [[ -f "${main_py}.pyc" ]]; then
    mv "${main_py}.pyc" "__main__.pyc"
else
    echo "Error: ${main_py}.pyc not found"
    exit 1
fi

python3 - <<EOF
import zipfile
import os

with zipfile.ZipFile("$output_pyz", "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for fname in os.listdir("."):
        if fname.endswith(".pyc"):
            zf.write(fname)
EOF
