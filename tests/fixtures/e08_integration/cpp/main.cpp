/* SPDX-License-Identifier: Apache-2.0 */
#include "project.hpp"
extern "C" int puts(const char *text);
int main() {
    const std::string message = project_label() + "_V1_" +
                                std::to_string(project_adjust(20, 22));
    puts(message.c_str());
    return 0;
}
