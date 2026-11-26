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
