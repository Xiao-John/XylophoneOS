// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstddef>
#include "../../browser_http/transport.hpp"

namespace clarke_https {
xos::i64 fetch(xos::u64 service, const browser_http::url& target, unsigned char* buffer,
               std::size_t capacity, xos::u64 deadline, browser_http::response& result);
}
