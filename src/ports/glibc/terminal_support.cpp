// SPDX-License-Identifier: Apache-2.0
// Freestanding bridge to the existing authenticated terminal application client.
#include "sysdeps/xos/xos_terminal_runtime.h"
#include <xos/terminal_client.hpp>
#include <xos/thread_abi.hpp>
#include <errno.h>
#include <fcntl.h>

namespace {
xos::terminal::client terminal_session{}; // Constant initialization, before init_array.
xos_u32 terminal_lock;
struct terminal_marker { xos_u64 magic; xos_u32 version, size; };
__attribute__((used, section(".xos.tty")))
const terminal_marker marker{xos::terminal_image_abi_magic, 1, sizeof(terminal_marker)};
static_assert(sizeof(marker) == 16);
static_assert(sizeof(xos_file_startup) == sizeof(xos::startup_info));
static_assert(sizeof(xos_file_startup_extension) == sizeof(xos::startup_extension));
static_assert(sizeof(xos_file_startup_descriptor) == sizeof(xos::startup_descriptor));
static_assert(sizeof(xos_terminal_mode) == sizeof(xos::terminal::mode));

long lock_terminal() {
    while (__atomic_exchange_n(&terminal_lock, 1, __ATOMIC_ACQUIRE) != 0) {
        const auto result = __xos_wait_word(&terminal_lock, 1, ~xos_u64{0});
        if (result != 0 && result != xos::thread_value_changed) return -EIO;
    }
    return 0;
}
void unlock_terminal() {
    __atomic_store_n(&terminal_lock, 0, __ATOMIC_RELEASE);
    (void)__xos_wake_word(&terminal_lock, 1);
}
long result_errno(xos::i64 result) {
    if (result >= 0) return static_cast<long>(result);
    switch (result) {
    case -1: return -EACCES;
    case -2: return -EINVAL;
    case -3: case -4: case -14: return -EAGAIN;
    case -5: case -17: return -ENOMEM;
    case -7: return -EPIPE;
    case -10: return -EPERM;
    case -11: case -12: return -EBUSY;
    case -13: return -ETIMEDOUT;
    case -16: return -EDEADLK;
    case -18: return -ENOTSUP;
    case xos::terminal::interrupted: return -EINTR;
    default: return -EIO;
    }
}
template<class function> long exchange(function invoke) {
    const long locked = lock_terminal();
    if (locked < 0) return locked;
    const long result = result_errno(invoke());
    unlock_terminal();
    return result;
}
}

extern "C" long __xos_terminal_restore(const xos_file_startup* startup) {
    return exchange([&] { return xos::terminal::connect_startup(terminal_session,
        reinterpret_cast<const xos::startup_info*>(startup)); });
}
extern "C" long __xos_terminal_close() {
    const long locked = lock_terminal();
    if (locked < 0) return locked;
    xos::terminal::close(terminal_session);
    unlock_terminal();
    return 0;
}
extern "C" long __xos_terminal_read(void* buffer, size_t length, unsigned int flags) {
    if ((flags & O_NONBLOCK) != 0) return -ENOTSUP;
    if (buffer == nullptr && length != 0) return -EFAULT;
    const auto amount = length > xos::terminal::data_bytes ? xos::terminal::data_bytes
        : static_cast<xos::u32>(length);
    return exchange([&] { return xos::terminal::read_mode(terminal_session, buffer, amount); });
}
extern "C" long __xos_terminal_write(const void* buffer, size_t length, unsigned int flags) {
    if ((flags & O_NONBLOCK) != 0) return -ENOTSUP;
    if (buffer == nullptr && length != 0) return -EFAULT;
    const auto amount = length > xos::terminal::data_bytes ? xos::terminal::data_bytes
        : static_cast<xos::u32>(length);
    return exchange([&] { return xos::terminal::write_until(terminal_session, buffer, amount,
        xos::thread_deadline_infinite); });
}
extern "C" long __xos_terminal_get_mode(xos_terminal_mode* output) {
    if (output == nullptr) return -EFAULT;
    xos::terminal::mode value{};
    const long result = exchange([&] { return xos::terminal::get_mode(terminal_session, value); });
    if (result == 0) *output = {value.iflag, value.oflag, value.cflag, value.lflag,
        value.ispeed, value.ospeed, value.vmin, value.vtime};
    return result;
}
extern "C" long __xos_terminal_set_mode(const xos_terminal_mode* input, unsigned int action) {
    if (input == nullptr) return -EFAULT;
    const xos::terminal::mode value{input->iflag, input->oflag, input->cflag, input->lflag,
        input->ispeed, input->ospeed, input->vmin, input->vtime};
    return exchange([&] { return xos::terminal::set_mode(terminal_session, value,
        static_cast<xos::terminal::mode_action>(action)); });
}
extern "C" long __xos_terminal_drain() {
    return exchange([] { return xos::terminal::drain(terminal_session); });
}
extern "C" long __xos_terminal_flush_input() {
    return exchange([] { return xos::terminal::flush_input(terminal_session); });
}
