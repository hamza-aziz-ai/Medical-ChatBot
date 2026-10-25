"""Rotating file logging: logs/<year>/<Month>/<name>.log, rolled over at midnight.

Each closed day is renamed to <name>.log.DD-MMM-YYYY in the folder it was written in, and
a new file starts in the folder for the current year and month. Names are spelled out in
English regardless of the system locale.
"""
import logging
import os
import re
import time
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

logger = logging.getLogger("app_logging")

# This project's modules; each gets its own log file named after it.
MODULES = frozenset({
    "main", "chatbot_graph_logic", "question_classifier", "question_parser",
    "answer_searcher", "database", "terms", "build_medicalgraph", "app_logging",
})

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
DEFAULT_LEVEL = "DEBUG"
DEFAULT_BACKUP_COUNT = 30
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def backup_suffix(day):
    return f"{day.day:02d}-{MONTHS[day.month - 1][:3]}-{day.year}"


class DayDateFormatter(logging.Formatter):
    """Timestamps like '25 October 2026, Sunday, 02:03:05.123 PM India Standard Time'.

    The timezone is the operating system's local name: an abbreviation such as IST on
    Linux and macOS, a full name such as India Standard Time on Windows.
    """

    def formatTime(self, record, datefmt=None):
        t = datetime.fromtimestamp(record.created).astimezone()
        hour = t.hour % 12 or 12
        meridiem = "AM" if t.hour < 12 else "PM"
        return (
            f"{t.day:02d} {MONTHS[t.month - 1]} {t.year}, {WEEKDAYS[t.weekday()]}, "
            f"{hour:02d}:{t:%M:%S}.{int(record.msecs):03d} {meridiem} {t.tzname()}"
        )


class MonthFolderRotatingHandler(TimedRotatingFileHandler):
    def __init__(self, log_dir, filename, backup_count=DEFAULT_BACKUP_COUNT):
        self.log_dir = Path(log_dir)
        self.filename = filename
        super().__init__(self.path_for(datetime.now()), when="midnight", backupCount=backup_count, encoding="utf-8", delay=True)

    def path_for(self, moment):
        folder = self.log_dir / str(moment.year) / MONTHS[moment.month - 1]
        folder.mkdir(parents=True, exist_ok=True)
        return str(folder / self.filename)

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None
        closed_day = datetime.fromtimestamp(self.rolloverAt - self.interval)
        current = Path(self.baseFilename)
        if current.exists():
            os.replace(current, current.with_name(f"{current.name}.{backup_suffix(closed_day)}"))
        self.baseFilename = self.path_for(datetime.now())
        self.delete_old_backups()
        self.rolloverAt = self.computeRollover(int(time.time()))

    def backups(self):
        pattern = re.compile(re.escape(self.filename) + r"\.(\d{2})-([A-Z][a-z]{2})-(\d{4})$")
        abbreviations = [month[:3] for month in MONTHS]
        found = []
        for path in self.log_dir.glob(f"*/*/{self.filename}.*"):
            match = pattern.match(path.name)
            if match and match.group(2) in abbreviations:
                day, month, year = int(match.group(1)), abbreviations.index(match.group(2)) + 1, int(match.group(3))
                found.append((datetime(year, month, day), path))
        return [path for _, path in sorted(found)]

    def delete_old_backups(self):
        if self.backupCount > 0:
            for path in self.backups()[:-self.backupCount]:
                path.unlink(missing_ok=True)


def log_level():
    name = os.environ.get("LOG_LEVEL", DEFAULT_LEVEL).upper()
    if name not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise RuntimeError("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")
    return name


class ModuleFileHandler(logging.Handler):
    """Routes each record to <module>.log for this project's modules, else to external.log."""

    def __init__(self, log_dir, backup_count=DEFAULT_BACKUP_COUNT):
        super().__init__()
        self.log_dir = log_dir
        self.backup_count = backup_count
        self.files = {}

    def file_for(self, logger_name):
        module = logger_name.split(".")[0]
        filename = f"{module}.log" if module in MODULES else "external.log"
        if filename not in self.files:
            handler = MonthFolderRotatingHandler(self.log_dir, filename, self.backup_count)
            handler.setFormatter(self.formatter)
            self.files[filename] = handler
        return self.files[filename]

    def emit(self, record):
        self.file_for(record.name).handle(record)

    def close(self):
        for handler in self.files.values():
            handler.close()
        super().close()


def setup_logging():
    """Attach the per-module file handler to the root logger once per process."""
    root = logging.getLogger()
    root.setLevel(log_level())
    if any(isinstance(handler, ModuleFileHandler) for handler in root.handlers):
        return
    raw_count = os.environ.get("LOG_BACKUP_COUNT", str(DEFAULT_BACKUP_COUNT))
    if not raw_count.isdigit():
        raise RuntimeError("LOG_BACKUP_COUNT must be a whole number of days (0 keeps every backup)")
    log_dir = os.environ.get("LOG_DIR") or DEFAULT_LOG_DIR
    handler = ModuleFileHandler(log_dir, int(raw_count))
    handler.setFormatter(DayDateFormatter(LOG_FORMAT))
    root.addHandler(handler)
    # The neo4j driver logs query parameters at DEBUG, and they can contain words from questions.
    logging.getLogger("neo4j").setLevel(logging.WARNING)
    logger.info("Logging to %s at level %s, keeping %s rotated file(s) per module", log_dir, logging.getLevelName(root.level), raw_count)
