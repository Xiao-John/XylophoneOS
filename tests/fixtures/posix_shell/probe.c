/* SPDX-License-Identifier: Apache-2.0 */
/* system()/popen()/pclose() against the installed dash shell. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static int missing_shell(void) {
    int ok = 1;
    const int status = system("true");
    ok = ok && status != -1 && WEXITSTATUS(status) == 127;
    errno = 0;
    FILE* stream = popen("true", "r");
    ok = ok && stream == NULL && errno == ENOENT;
    puts(ok ? "POSIX_SHELL_MISSING_OK" : "POSIX_SHELL_MISSING_FAILED");
    return ok ? 0 : 1;
}

int main(int argc, char** argv) {
    if (argc > 1 && strcmp(argv[1], "no-shell") == 0) { return missing_shell(); }

    int failures = 0;
    int status = system("true");
    const int true_ok = status == 0;

    status = system("exit 3");
    const int exit_ok = status != -1 && WEXITSTATUS(status) == 3;

    status = system("nosuchcommand-xyz");
    const int missing_ok = status != -1 && WEXITSTATUS(status) == 127;

    const int null_ok = system(NULL) != 0;

    char buffer[64] = {0};
    FILE* stream = popen("echo hi", "r");
    if (stream != NULL) { (void)fgets(buffer, sizeof(buffer), stream); }
    status = stream != NULL ? pclose(stream) : -1;
    const int read_ok = strcmp(buffer, "hi\n") == 0 && status == 0;

    stream = popen("read value && [ \"$value\" = value ] && exit 7; exit 9", "w");
    int write_ok = 0;
    if (stream != NULL && fputs("value\n", stream) >= 0) {
        status = pclose(stream);
        write_ok = status != -1 && WEXITSTATUS(status) == 7;
    } else if (stream != NULL) {
        (void)pclose(stream);
    }

    failures += !true_ok + !exit_ok + !missing_ok + !null_ok + !read_ok + !write_ok;
    printf("true=%d exit3=%d missing=%d null=%d read=%d write=%d\n",
           true_ok, exit_ok, missing_ok, null_ok, read_ok, write_ok);
    puts(failures == 0 ? "POSIX_SHELL_OK" : "POSIX_SHELL_FAILED");
    return failures == 0 ? 0 : 1;
}
