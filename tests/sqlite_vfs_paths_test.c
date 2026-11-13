/* SPDX-License-Identifier: Apache-2.0 */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include <sqlite3.h>

static void sql(sqlite3 *database, const char *statement) {
    int result = sqlite3_exec(database, statement, 0, 0, 0);
    if (result != SQLITE_OK) fprintf(stderr, "%s: %s\n", statement, sqlite3_errmsg(database));
    assert(result == SQLITE_OK);
}

int main(void) {
    assert(sqlite3_initialize() == SQLITE_OK);
    sqlite3_vfs *vfs = sqlite3_vfs_find("xos");
    assert(vfs != 0);
    char cwd[256], path[256], expected[256], journal[256];
    assert(getcwd(cwd, sizeof(cwd)) != 0);
    assert(snprintf(expected, sizeof(expected), "%s/database.db", cwd) < (int)sizeof(expected));
    assert(snprintf(journal, sizeof(journal), "%s-journal", expected) < (int)sizeof(journal));
    assert(vfs->xFullPathname(vfs, "./sub/../database.db", sizeof(path), path) == SQLITE_OK);
    assert(strcmp(path, expected) == 0);
    assert(vfs->xFullPathname(vfs, "/../../db//./new.db", sizeof(path), path) == SQLITE_OK);
    assert(strcmp(path, "/db/new.db") == 0);
    assert(vfs->xFullPathname(vfs, "database.db", 1, path) == SQLITE_CANTOPEN);
    assert(vfs->xFullPathname(vfs, "database.db", 0, path) == SQLITE_CANTOPEN);

    assert(mkdir("sub", 0700) == 0);
    sqlite3 *first = 0, *second = 0;
    assert(sqlite3_open("./sub/../database.db", &first) == SQLITE_OK);
    sql(first, "CREATE TABLE records(value INTEGER)");
    assert(sqlite3_open(expected, &second) == SQLITE_OK);
    sql(first, "BEGIN IMMEDIATE");
    assert(sqlite3_exec(second, "BEGIN IMMEDIATE", 0, 0, 0) == SQLITE_BUSY);
    sql(first, "ROLLBACK");
    sql(second, "BEGIN IMMEDIATE; ROLLBACK");
    assert(sqlite3_close(second) == SQLITE_OK);

    /* Host hard links exercise identical file identity with different names;
       XOS uses that identity for its FAT case/short-name aliases, not links. */
    assert(link(expected, "alias.db") == 0);
    assert(sqlite3_open("alias.db", &second) == SQLITE_OK);
    sql(first, "BEGIN IMMEDIATE");
    assert(sqlite3_exec(second, "BEGIN IMMEDIATE", 0, 0, 0) == SQLITE_BUSY);
    sql(first, "ROLLBACK");
    assert(sqlite3_close(second) == SQLITE_OK);

    assert(chdir("sub") == 0);
    sql(first, "BEGIN IMMEDIATE; INSERT INTO records VALUES(42)");
    assert(access(journal, F_OK) == 0);
    assert(access("database.db-journal", F_OK) != 0);
    sql(first, "COMMIT");
    assert(sqlite3_close(first) == SQLITE_OK);
    assert(sqlite3_shutdown() == SQLITE_OK);
    puts("PASS SQLite VFS: canonical paths, alias locks, released locks, journal after cwd change");
    return 0;
}
