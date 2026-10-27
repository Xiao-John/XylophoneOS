# SPDX-License-Identifier: Apache-2.0
"""First-boot database workload and post-sync reboot verification."""

import sqlite3
import sys
from pathlib import Path


ROOT = Path("/work/py3b3")
DATABASE = ROOT / "persistent.db"
CORRUPT = ROOT / "corrupt.db"


def open_database():
    # sqlite3.connect() does not expose SQLite's VFS selector. The statically
    # linked XOS VFS registers itself as the process default during init.
    return sqlite3.connect(str(DATABASE), timeout=0.05)


def first_boot():
    assert sqlite3.sqlite_version_info == (3, 54, 1), sqlite3.sqlite_version
    connection = open_database()
    connection.execute("CREATE TABLE records (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("CREATE TABLE unique_values (value TEXT UNIQUE NOT NULL)")
    connection.execute("INSERT INTO records VALUES (?, ?)", ("boot", "first"))
    connection.commit()

    connection.execute("BEGIN")
    connection.execute("INSERT INTO records VALUES (?, ?)", ("rolled_back", "no"))
    connection.rollback()
    assert connection.execute("SELECT count(*) FROM records WHERE key='rolled_back'").fetchone()[0] == 0

    connection.execute("INSERT INTO unique_values VALUES ('once')")
    connection.commit()
    try:
        connection.execute("INSERT INTO unique_values VALUES ('once')")
    except sqlite3.IntegrityError:
        connection.rollback()
    else:
        raise AssertionError("UNIQUE constraint violation was accepted")
    connection.close()

    blocker = open_database()
    blocker.execute("BEGIN EXCLUSIVE")
    blocker.execute("INSERT INTO records VALUES (?, ?)", ("locked", "committed"))
    contender = None
    try:
        contender = open_database()
        contender.execute("BEGIN EXCLUSIVE")
    except sqlite3.OperationalError as error:
        assert "locked" in str(error).lower() or "busy" in str(error).lower(), repr(error)
    else:
        raise AssertionError("a second exclusive writer did not receive SQLITE_BUSY")
    if contender is not None:
        contender.close()
    blocker.commit()
    blocker.close()
    connection.close()

    CORRUPT.write_bytes(b"not a SQLite database\x00" * 19)
    corrupt = sqlite3.connect(str(CORRUPT))
    try:
        corrupt.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("corrupt database was accepted")
    finally:
        corrupt.close()
    print("PY3_B3_FIRST_OK create commit rollback unique busy corrupt")


def after_reboot():
    connection = open_database()
    rows = connection.execute("SELECT key, value FROM records ORDER BY key").fetchall()
    assert rows == [("boot", "first"), ("locked", "committed")], rows
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert connection.execute("SELECT value FROM unique_values").fetchone() == ("once",)
    connection.close()
    print("PY3_B3_REOPEN_OK sync reboot persistent integrity")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("first", "reopen"):
        raise SystemExit("usage: sqlite_probe.py first|reopen")
    if sys.argv[1] == "first":
        first_boot()
    else:
        after_reboot()
