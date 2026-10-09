#!/bin/bash
export DYLD_LIBRARY_PATH=/opt/homebrew/opt/cairo/lib
# Set PYTHON to use a specific interpreter; the default is python3 on PATH.
"${PYTHON:-python3}" gui.py
