/* SPDX-License-Identifier: Apache-2.0 */
#include "state.hpp"
#include <cstdio>

namespace {
int constructed = 0;
struct lifetime_probe {
    lifetime_probe() { ++constructed; }
    ~lifetime_probe() {
        --constructed;
        char tls_text[32]{};
        FILE* tls_marker = std::fopen("/out/cpp_tls_destructor.marker", "rb");
        const bool tls_first = tls_marker && std::fgets(tls_text, sizeof(tls_text), tls_marker) &&
                               tls_text[0] == 't' && tls_text[1] == 'l' && tls_text[2] == 's';
        if (tls_marker) std::fclose(tls_marker);
        FILE* marker = std::fopen("/out/cpp_global_destructor.marker", "wb");
        if (marker) {
            std::fputs(constructed == 0 && tls_first ? "destructed\n" : "bad\n", marker);
            std::fclose(marker);
        }
    }
};
lifetime_probe global_probe;
}

int translation_unit_value() { return 42; }
int construction_count() { return constructed; }
int destruction_count() { return constructed; }
