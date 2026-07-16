"""Launcher kept for backwards compatibility: python cli.py <args>"""
from diastasis.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
