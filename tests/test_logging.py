import logging
import os
import time
from datetime import datetime

import pytest

import app_logging
from app_logging import DayDateFormatter, ModuleFileHandler, MonthFolderRotatingHandler


def record_at(moment, level=logging.DEBUG, message="hello"):
    record = logging.LogRecord("test", level, __file__, 1, message, None, None)
    record.created = moment.timestamp()
    record.msecs = moment.microsecond // 1000
    return record


@pytest.mark.parametrize("moment, clock", [
    (datetime(2026, 10, 25, 9, 5, 7, 42000), "09:05:07.042 AM"),
    (datetime(2026, 10, 25, 13, 5, 7, 900000), "01:05:07.900 PM"),
    (datetime(2026, 10, 25, 0, 0, 0, 1000), "12:00:00.001 AM"),
    (datetime(2026, 10, 25, 12, 30, 0, 0), "12:30:00.000 PM"),
])
def test_timestamp_and_level_format(moment, clock):
    formatter = DayDateFormatter(app_logging.LOG_FORMAT)
    zone = moment.astimezone().tzname()
    assert formatter.format(record_at(moment)) == f"25 October 2026, Sunday, {clock} {zone} [DEBUG] test: hello"


def test_files_go_into_year_and_month_folders(tmp_path):
    handler = MonthFolderRotatingHandler(tmp_path, "api.log")
    now = datetime.now()
    expected = tmp_path / str(now.year) / app_logging.MONTHS[now.month - 1] / "api.log"
    assert handler.baseFilename == str(expected)
    handler.emit(record_at(now))
    handler.close()
    assert expected.read_text(encoding="utf-8")


def test_rollover_names_the_closed_day_and_starts_a_new_file(tmp_path):
    handler = MonthFolderRotatingHandler(tmp_path, "api.log")
    handler.setFormatter(DayDateFormatter(app_logging.LOG_FORMAT))
    handler.emit(record_at(datetime.now(), message="yesterday"))
    # Pretend the open file belongs to 31 October 2026 and its midnight has passed.
    old = tmp_path / "2026" / "October" / "api.log"
    old.parent.mkdir(parents=True, exist_ok=True)
    handler.close()
    os.replace(handler.baseFilename, old)
    handler.baseFilename = str(old)
    handler.rolloverAt = datetime(2026, 11, 1).timestamp()
    handler.doRollover()
    handler.emit(record_at(datetime.now(), message="today"))
    handler.close()
    assert (tmp_path / "2026" / "October" / "api.log.31-Oct-2026").read_text(encoding="utf-8").count("yesterday") == 1
    assert "today" in open(handler.baseFilename, encoding="utf-8").read()
    assert handler.rolloverAt > time.time()


def test_old_backups_are_deleted_across_folders(tmp_path):
    for year, month, day in [(2025, "December", 30), (2025, "December", 31), (2026, "January", 1)]:
        folder = tmp_path / str(year) / month
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"api.log.{day:02d}-{month[:3]}-{year}").write_text("x", encoding="utf-8")
    (tmp_path / "2026" / "January" / "other.log.01-Jan-2026").write_text("x", encoding="utf-8")
    handler = MonthFolderRotatingHandler(tmp_path, "api.log", backup_count=2)
    handler.delete_old_backups()
    handler.close()
    remaining = sorted(p.name for p in tmp_path.rglob("*.log.*"))
    assert remaining == ["api.log.01-Jan-2026", "api.log.31-Dec-2025", "other.log.01-Jan-2026"]


def test_default_level_is_debug_and_invalid_levels_are_refused(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert app_logging.log_level() == "DEBUG"
    monkeypatch.setenv("LOG_LEVEL", "info")
    assert app_logging.log_level() == "INFO"
    monkeypatch.setenv("LOG_LEVEL", "loud")
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        app_logging.log_level()


def test_setup_attaches_one_handler_and_keeps_driver_parameters_out(monkeypatch, tmp_path):
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    try:
        app_logging.setup_logging()
        app_logging.setup_logging()
        handlers = [h for h in root.handlers if isinstance(h, ModuleFileHandler)]
        assert len(handlers) == 1
        assert root.level == logging.DEBUG
        assert logging.getLogger("neo4j").level == logging.WARNING
    finally:
        for handler in root.handlers[:]:
            if handler not in saved_handlers:
                handler.close()
                root.removeHandler(handler)
        root.setLevel(saved_level)


def test_each_module_logs_to_its_own_file(tmp_path):
    handler = ModuleFileHandler(tmp_path)
    handler.setFormatter(DayDateFormatter(app_logging.LOG_FORMAT))
    now = datetime.now()
    for name in ("main", "question_parser", "build_medicalgraph", "werkzeug", "neo4j.io"):
        record = record_at(now, message=f"from {name}")
        record.name = name
        handler.handle(record)
    handler.close()
    folder = tmp_path / str(now.year) / app_logging.MONTHS[now.month - 1]
    assert sorted(p.name for p in folder.iterdir()) == ["build_medicalgraph.log", "external.log", "main.log", "question_parser.log"]
    assert "from question_parser" in (folder / "question_parser.log").read_text(encoding="utf-8")
    external = (folder / "external.log").read_text(encoding="utf-8")
    assert "from werkzeug" in external and "from neo4j.io" in external
    assert "from main" not in external


def test_every_project_module_has_a_log_file():
    from pathlib import Path
    modules = {p.stem for p in (Path(app_logging.__file__).parent).glob("*.py")}
    assert modules == set(app_logging.MODULES)
