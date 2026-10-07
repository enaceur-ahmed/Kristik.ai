"""
Centralised logging setup.
"""
import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    # Windows consoles default to cp1252, but log messages contain
    # Unicode (e.g. arrows "→" in transformer step summaries).
    # Force UTF-8 output so logging never raises UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream.encoding and stream.encoding.lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    logging.basicConfig(stream=sys.stdout, level=getattr(logging, level), format=fmt)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
