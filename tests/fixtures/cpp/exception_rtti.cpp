/* SPDX-License-Identifier: Apache-2.0 */
#include <typeinfo>

extern void throw_from_cpp_archive(int* destroyed);

namespace {
int unwind_count = 0;
struct unwind_probe {
    ~unwind_probe() { ++unwind_count; }
};
struct base { virtual ~base() = default; };
struct derived : base {};

__attribute__((noinline)) void unwind_middle_frame() {
    unwind_probe probe;
    throw_from_cpp_archive(&unwind_count);
}
}

int exception_unwind_probe() {
    try {
        unwind_middle_frame();
    } catch (int value) {
        return value == 3 && unwind_count == 2 ? unwind_count + 1 : -1;
    }
}

int rtti_probe() {
    derived object;
    base* pointer = &object;
    return dynamic_cast<derived*>(pointer) && typeid(*pointer) == typeid(derived) ? 7 : -1;
}
