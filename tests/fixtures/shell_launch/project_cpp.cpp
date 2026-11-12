// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <string>
#include <vector>

int project_cpp_value();
void project_throw();
extern thread_local int project_tls_value;
int project_tls_increment(int value);
namespace {
int destroyed;
struct lifetime { ~lifetime() { ++destroyed; } };
struct base { virtual ~base() = default; };
struct derived : base {};
}
int main() {
    std::vector<int> values{19, 23};
    std::string text = "native C++";
    derived object;
    base* pointer = &object;
    if (values[0] + values[1] != project_cpp_value() || text.size() != 10 ||
        dynamic_cast<derived*>(pointer) == nullptr || project_tls_value != 7 ||
        project_tls_increment(5) != 12 || project_tls_value != 12) return 1;
    try {
        lifetime frame;
        project_throw();
    } catch (int value) {
        if (value != 42 || destroyed != 1) return 2;
        std::puts("SL3_CPP_OK");
        return 0;
    }
    return 3;
}
