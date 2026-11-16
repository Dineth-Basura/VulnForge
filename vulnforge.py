#!/usr/bin/env python3
"""VulnForge entry point — Automated Web Pentesting Framework, created by dineth.

Usage:
    ./vulnforge.py scan example.com
    ./vulnforge.py modules
    ./vulnforge.py check
"""
import sys
from pathlib import Path

# allow running from anywhere without installing
sys.path.insert(0, str(Path(__file__).resolve().parent))

from vforge.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
