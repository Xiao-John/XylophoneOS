/* SPDX-License-Identifier: Apache-2.0 */
/* system()/popen()/pclose() against the installed dash shell. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

int main(void) {
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
    if (stream != nullptr) { (void)fgets(buffer, sizeof(buffer), stream); }
    status = stream != nullptr ? pclose(stream) : -1;
    const int read_ok = strcmp(buffer, "hi\n") == 0 && status == 0;

    stream = popen("read value; exit 7", "w");
    if (stream != nullptr) { (void)fputs("value\n", stream); }
    status = stream != nullptr ? pclose(stream) : -1;
    const int write_ok = status != -1 && WEXITSTATUS(status) == 7;

    failures += !true_ok + !exit_ok + !missing_ok + !null_ok + !read_ok + !write_ok;
    printf("true=%d exit3=%d missing=%d null=%d read=%d write=%d\n",
           true_ok, exit_ok, missing_ok, null_ok, read_ok, write_ok);
    puts(failures == 0 ? "POSIX_SHELL_OK" : "POSIX_SHELL_FAILED");
    return failures == 0 ? 0 : 1;
}
