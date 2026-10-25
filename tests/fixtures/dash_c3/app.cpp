// SPDX-License-Identifier: Apache-2.0
#include <string>
#include <cstdio>
#include "value.h"
int main() { std::string text("C3_CPP real_gxx"); std::printf("%s value=%d\n",text.c_str(),C3_VALUE); return C3_VALUE!=42; }
