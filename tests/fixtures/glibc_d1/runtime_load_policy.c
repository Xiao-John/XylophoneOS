/* SPDX-License-Identifier: Apache-2.0 */
#define _GNU_SOURCE 1
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>

static int observe(const char *name, void *handle)
{
    const char *error = dlerror();
    if (handle != NULL) {
        printf("D2_LOAD %s opened\n", name);
        int result = dlclose(handle);
        error = dlerror();
        printf("D2_CLOSE %s %d %s\n", name, result, error == NULL ? "-" : error);
        return 0;
    }
    printf("D2_LOAD %s refused %s\n", name, error == NULL ? "-" : error);
    return error != NULL && strstr(error, "XOS fixed closure") != NULL
        && strstr(error, strerror(ENOTSUP)) != NULL && dlerror() == NULL;
}

int main(void)
{
    (void)dlerror();
    int refused = observe("main", dlopen(NULL, RTLD_NOW));
    (void)dlerror();
    refused += observe("loaded", dlopen("libc.so.0.1", RTLD_NOW));
    (void)dlerror();
    refused += observe("namespace", dlmopen(LM_ID_BASE, "libc.so.0.1", RTLD_NOW));
    (void)dlerror();
    refused += observe("missing", dlopen("libxos-d2-absent.so", RTLD_NOW));
    printf("D2_LOAD_POLICY_OBSERVED %d\n", refused);
    return 0;
}
