// SPDX-License-Identifier: Apache-2.0
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

extern "C" int __cxa_thread_atexit(void (*function)(void*), void* object, void* dso);

namespace {
void print_marker(const char* marker) { puts(marker); }

void late_tls_destructor(void*) { print_marker("[tls_exit] tls_late_dtor"); }

struct tls_item {
    explicit tls_item(int value) : value(value) {}
    ~tls_item() {
        if (value == 2) {
            print_marker("[tls_exit] tls_b_dtor");
            if (__cxa_thread_atexit(late_tls_destructor, nullptr, nullptr) != 0) {
                print_marker("[tls_exit] FAIL late_registration");
            }
        } else {
            print_marker("[tls_exit] tls_a_dtor");
        }
    }
    int value;
};

thread_local tls_item tls_a(1);
thread_local tls_item tls_b(2);

struct global_item {
    global_item() { print_marker("[tls_exit] global_ctor"); }
    ~global_item() { print_marker("[tls_exit] global_dtor"); }
};

global_item global_instance;

void ordinary_exit_handler() { print_marker("[tls_exit] atexit_handler"); }
void fini_probe() { print_marker("[tls_exit] fini"); }
using fini_function = void (*)();
__attribute__((used, section(".fini_array.00100"))) fini_function fini_entry = fini_probe;
}

int main(int argc, char** argv) {
    if (argc > 1 && argv[1] != nullptr && strcmp(argv[1], "exit") == 0) {
        if (tls_a.value != 1 || tls_b.value != 2) {
            print_marker("[tls_exit] FAIL tls_init");
            return 1;
        }
        if (atexit(ordinary_exit_handler) != 0) {
            print_marker("[tls_exit] FAIL atexit_registration");
            return 2;
        }
        print_marker("[tls_exit] explicit_exit");
        exit(0);
    }

    if (tls_a.value != 1 || tls_b.value != 2) {
        print_marker("[tls_exit] FAIL tls_init");
        return 1;
    }
    if (atexit(ordinary_exit_handler) != 0) {
        print_marker("[tls_exit] FAIL atexit_registration");
        return 2;
    }
    print_marker("[tls_exit] main_return");
    return 0;
}
