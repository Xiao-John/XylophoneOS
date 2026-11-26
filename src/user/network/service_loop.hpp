// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "../drivers/virtio_net.hpp"
namespace xos::user::network {
struct frame_io;
frame_io network_frame_io(virtio_net::driver& nic);
i64 serve(u64 controller, virtio_net::driver& nic);
#ifdef XOS_NET_DNS_PROBE
i64 probe_dns(virtio_net::driver& nic);
#endif
}
