"""Kompatibilitäts-Shim: UI liegt jetzt in app.py, Logik in den Modulen."""

from app import main

if __name__ == "__main__":
    main()
