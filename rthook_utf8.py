# -*- coding: utf-8 -*-
"""
PyInstaller runtime hook to ensure UTF-8 encoding across all streams and locale.
Prevents UnicodeEncodeError / UnicodeDecodeError when launched from macOS Finder.
"""
import os
import sys
import locale

# 1. Force UTF-8 environment variables
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")
if not os.environ.get("LANG"):
    os.environ["LANG"] = "ko_KR.UTF-8"
if not os.environ.get("LC_ALL"):
    os.environ["LC_ALL"] = "ko_KR.UTF-8"
if not os.environ.get("LC_CTYPE"):
    os.environ["LC_CTYPE"] = "UTF-8"

# 2. Reconfigure standard streams to UTF-8 with replacement for invalid chars
for _stream in (sys.stdin, sys.stdout, sys.stderr):
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 3. Best-effort locale initialization
for _loc in ("", "ko_KR.UTF-8", "en_US.UTF-8", "C.UTF-8", "UTF-8"):
    try:
        locale.setlocale(locale.LC_ALL, _loc)
        break
    except Exception:
        pass

