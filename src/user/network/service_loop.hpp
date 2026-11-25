// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../drivers/virtio_net.hpp"
namespace xos::user::network { i64 serve(u64 controller, virtio_net::driver& nic); }
