// SPDX-License-Identifier: Apache-2.0
int project_cpp_value() { return 42; }
void project_throw() { throw 42; }
thread_local int project_tls_value = 7;
int project_tls_increment(int value) { project_tls_value += value; return project_tls_value; }
