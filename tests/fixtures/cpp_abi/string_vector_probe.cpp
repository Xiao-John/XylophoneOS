// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <string>
#include <vector>

int main() {
    std::string text("xylophone");
    std::vector<int> values;
    values.push_back(17);
    values.push_back(25);
    if (text != "xylophone" || values.size() != 2 || values[0] != 17 || values[1] != 25) {
        std::puts("[cpp_abi] string_vector=fail");
        return 1;
    }
    std::puts("[cpp_abi] string_vector=ok");
    return 0;
}
