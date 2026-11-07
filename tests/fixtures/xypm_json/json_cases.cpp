// SPDX-License-Identifier: Apache-2.0
// Host regression for the xypm JSON integer boundaries.
#include <climits>
#include <csetjmp>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include "../../../src/user/programs/xypm_native.hpp"

using namespace xypm_native;

static int failures;

static bool parse_number(const char* text, int64_t& number) {
    jmp_buf target;
    jmp_buf* previous = error_target;
    error_target = &target;
    bool ok = false;
    if (setjmp(target) == 0) {
        json_parser parser(text, std::strlen(text));
        value* root = parser.parse();
        if (root != nullptr && root->type == kind::number) {
            number = root->number;
            ok = true;
        }
    }
    error_target = previous;
    return ok;
}

static bool parse_array_first_number(const char* text, int64_t& number) {
    jmp_buf target;
    jmp_buf* previous = error_target;
    error_target = &target;
    bool ok = false;
    if (setjmp(target) == 0) {
        json_parser parser(text, std::strlen(text));
        value* root = parser.parse();
        if (root != nullptr && root->type == kind::array && root->child != nullptr &&
            root->child->type == kind::number) {
            number = root->child->number;
            ok = true;
        }
    }
    error_target = previous;
    return ok;
}

static void expect_value(const char* text, int64_t expected) {
    int64_t number = 0;
    if (!parse_number(text, number) || number != expected) {
        std::fprintf(stderr, "FAIL value %s got %lld expected %lld\n", text,
                     static_cast<long long>(number), static_cast<long long>(expected));
        ++failures;
    }
}

static void expect_error(const char* text) {
    int64_t number = 0;
    if (parse_number(text, number)) {
        std::fprintf(stderr, "FAIL expected overflow for %s got %lld\n", text,
                     static_cast<long long>(number));
        ++failures;
    }
}

int main() {
    expect_value("0", 0);
    expect_value("-0", 0);
    expect_value("9223372036854775807", INT64_MAX);
    expect_value("-9223372036854775808", INT64_MIN);
    expect_error("9223372036854775808");
    expect_error("-9223372036854775809");
    int64_t number = 0;
    if (!parse_array_first_number("[-9223372036854775808]", number) || number != INT64_MIN) {
        std::fprintf(stderr, "FAIL array INT64_MIN\n");
        ++failures;
    }
    if (failures != 0) { return 1; }
    std::printf("XYPm_JSON_CASES_PASSED=7\n");
    return 0;
}
