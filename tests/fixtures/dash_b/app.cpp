/* SPDX-License-Identifier: Apache-2.0 */
#include <stdio.h>
#include <string>
int main() {
    std::string value = "toolchain";
    printf("cpp_app=%s\n", value.c_str());
    return value == "toolchain" ? 0 : 1;
}
