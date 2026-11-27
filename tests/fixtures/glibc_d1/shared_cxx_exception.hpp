// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdexcept>

class sample_error final : public std::runtime_error {
public:
    sample_error();
    ~sample_error() override;
};

[[noreturn]] void throw_sample_error();
int exception_sample_state();
unsigned exception_sample_destroyed();
bool exception_sample_init_worker_tls(unsigned id);
bool exception_sample_worker_tls_matches(unsigned id);
