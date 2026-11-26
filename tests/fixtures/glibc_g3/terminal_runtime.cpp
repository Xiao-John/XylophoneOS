// SPDX-License-Identifier: Apache-2.0
// Production FD/termios/native client; only kernel channels and files peer are simulated.
#include "xos_file_runtime.h"
#include "xos_terminal_runtime.h"
#include <xos/terminal_client.hpp>
#include <xos/thread_abi.hpp>
#include <atomic>
#include <cassert>
#include <cerrno>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <condition_variable>
#include <fcntl.h>
#include <linux/futex.h>
#include <mutex>
#include <sys/ioctl.h>
#include <sys/select.h>
#include <sys/syscall.h>
#include <thread>
#include <unistd.h>

extern "C" { const void *__xos_startup = nullptr; }
extern "C" int xos_test_ioctl(int, unsigned long, ...);
extern "C" int xos_test_select(int, fd_set*, fd_set*, fd_set*, timeval*);
namespace {
alignas(16) unsigned char startup_area[4096];
std::mutex mock_lock;
std::condition_variable input_changed;
xos::channel_info channels[3];
unsigned channel_count = 2, channel_queries, channel_closes, sends, file_closes, file_sends;
xos::terminal::request pending;
xos::terminal::mode mode = xos::terminal::default_mode;
xos_file_response file_response;
xos::u64 next_sequence = 1;
xos::i64 readiness_reply;
bool pending_reply, block_read, read_waiting, input_ready;
const char *failure = "";
bool fail_once;

void setup(unsigned version = 2) {
    __xos_startup = startup_area;
    auto *startup = reinterpret_cast<xos_file_startup *>(startup_area);
    *startup = {xos::startup_magic, version, sizeof(*startup), 0, 3, 0, {0, 1, 2}, 64};
    auto *extension = reinterpret_cast<xos_file_startup_extension *>(startup_area + 64);
    *extension = {xos::startup_extension_magic, 0, 0x10007, 0, 0, {0,0,0}, {0,0,0}, {0,0,0}, 10};
    channels[0] = {xos::channel_version, sizeof(xos::channel_info), 10, xos::channel_send, 2, 1};
    channels[1] = {xos::channel_version, sizeof(xos::channel_info), 11, xos::channel_receive, 2, 1};
    if (version == 3) {
        extension->flags = 0x10000;
        auto *execution = reinterpret_cast<xos_file_startup_exec *>(startup_area + 152);
        *execution = {xos::startup_exec_magic, reinterpret_cast<xos_u64>(startup_area + 256), 2, 0};
        auto *state = reinterpret_cast<xos::startup_terminal_exec_extension *>(startup_area + 176);
        *state = {xos::startup_terminal_exec_magic, 42};
        auto *items = reinterpret_cast<xos_file_startup_descriptor *>(startup_area + 256);
        items[0] = {2, 0, 5, 0, O_RDWR, 0};
        items[1] = {9, 0, 5, 0, O_RDWR, 0};
        next_sequence = 42;
    }
}
bool is(const char *name) { return std::strcmp(failure, name) == 0; }

void file_request(const xos_file_request& request) {
    ++file_sends;
    file_response = {};
    file_response.magic = 0x53455246;
    file_response.version = 2;
    file_response.request_id = request.request_id;
    if (request.operation == 4) { file_response.handle = 7; file_response.reserved = 1; }
    else if (request.operation == 6) file_response.value = request.length;
    else if (request.operation == 8) ++file_closes;
    else std::abort();
}
}

extern "C" int __xos_file_test_startup_range(xos_u64 address, xos_u64 length) {
    const auto begin = reinterpret_cast<xos_u64>(startup_area);
    return address >= begin && address <= begin + sizeof(startup_area)
        && length <= begin + sizeof(startup_area) - address;
}
extern "C" long __xos_clock_test_trap(unsigned long number, unsigned long first) {
    assert(number == 46 && first == 0);
    return 1000;
}
extern "C" xos_i64 __xos_wait_word(xos_u32* address, xos_u32 expected, xos_u64) {
    const long result = syscall(SYS_futex, address, FUTEX_WAIT_PRIVATE, expected, nullptr, nullptr, 0);
    return result == 0 ? 0 : errno == EAGAIN ? -14 : -11;
}
extern "C" xos_i64 __xos_wake_word(xos_u32* address, xos_u32 count) {
    return syscall(SYS_futex, address, FUTEX_WAKE_PRIVATE, count, nullptr, nullptr, 0);
}
extern "C" long __xos_file_test_trap(xos_u64 number, xos_u64 first, xos_u64 second, xos_u64 third) {
    std::unique_lock<std::mutex> guard(mock_lock);
    if (number == 6) return 77;
    if (number == 22) { auto *handles = reinterpret_cast<xos_u32*>(first); handles[0]=100; handles[1]=101; return 0; }
    if (number == 46) return 1000;
    if (number == 4 && first == 100) { file_request(*reinterpret_cast<const xos_file_request*>(second)); return 0; }
    if (number == 5 && first == 101) { std::memcpy(reinterpret_cast<void*>(second), &file_response, sizeof(file_response)); return sizeof(file_response); }
    if (number == xos::sys_channel) {
        if (first == static_cast<xos_u64>(xos::channel_action::enumerate)) {
            ++channel_queries;
            if (second >= channel_count) return xos::thread_error_not_found;
            *reinterpret_cast<xos::channel_info*>(third) = channels[second]; return 0;
        }
        if (first == static_cast<xos_u64>(xos::channel_action::close)) {
            assert(second == 10 || second == 11); ++channel_closes; return 0;
        }
        if (first == static_cast<xos_u64>(xos::channel_action::wait)) {
            assert(second == 10 || second == 11);
            if (second == 11 && fail_once && (is("service_death") || is("timeout"))) {
                fail_once = false; return is("timeout") ? -13 : -1;
            }
            if (second == 11 && block_read && pending.operation == 12) {
                read_waiting = true; input_changed.notify_all();
                input_changed.wait(guard, [] { return input_ready; });
            }
            return 0;
        }
    }
    if (number == 4 && first == 10) {
        assert(!pending_reply && third == sizeof(pending));
        pending = *reinterpret_cast<const xos::terminal::request*>(second);
        assert(pending.version == 2 && pending.size == sizeof(pending));
        assert(pending.sequence == next_sequence++);
        ++sends; pending_reply = true; return 0;
    }
    if (number == 5 && first == 11) {
        assert(pending_reply && third == sizeof(xos::terminal::response));
        auto& reply = *reinterpret_cast<xos::terminal::response*>(second);
        reply = {}; reply.version = 2; reply.size = sizeof(reply); reply.sequence = pending.sequence;
        if (pending.operation == 10) { reply.length = sizeof(mode); std::memcpy(reply.data, &mode, sizeof(mode)); }
        else if (pending.operation == 11) { std::memcpy(&mode, pending.data, sizeof(mode)); assert(pending.deadline_ns <= 2); }
        else if (pending.operation == 12) {
            if (mode.vmin != 0 || block_read) { reply.result = 1; reply.length = 1; reply.data[0] = 'R'; }
        } else if (pending.operation == 7) reply.result = pending.length > 17 ? 17 : pending.length;
        else if (pending.operation == 15) { assert(pending.length == 0); reply.result = readiness_reply; }
        else assert(pending.operation == 13 || pending.operation == 14);
        pending_reply = false;
        if (fail_once) {
            fail_once = false;
            if (is("wrong_sequence")) ++reply.sequence;
            if (is("reserved")) reply.reserved = 1;
            if (is("unknown_status")) { reply.result = -99; reply.length = 0; }
            if (is("bad_mode")) reply.data[0] = 1;
            if (is("overread")) { reply.result = 2; reply.length = 2; }
            if (is("zero_write")) reply.result = 0;
            if (is("interrupted")) { reply.result = -19; reply.length = 0; }
            if (is("short_reply")) return sizeof(reply) - 1;
        }
        return sizeof(reply);
    }
    std::abort();
}
namespace xos::sdk {
i64 syscall(u64 number, u64 first, u64 second, u64 third) {
    return __xos_file_test_trap(number, first, second, third);
}
}

int main(int argc, char **argv) {
    assert(argc == 2);
    failure = argv[1];
    if (is("v3") || is("invalid_v3") || is("missing_flag") || is("missing_object") || is("zero_sequence")) {
        setup(3);
        auto *extension = reinterpret_cast<xos_file_startup_extension*>(startup_area + 64);
        auto *execution = reinterpret_cast<xos_file_startup_exec*>(startup_area + 152);
        auto *items = reinterpret_cast<xos_file_startup_descriptor*>(startup_area + 256);
        if (is("v3")) {
            struct termios value{};
            assert(__xos_terminal_tcgetattr(9, &value) == 0 && sends == 1 && next_sequence == 43);
            assert(__xos_file_isatty(0) == -EBADF);
            assert(__xos_file_close(9) == 0 && channel_closes == 0);
            assert(__xos_file_write(2, "ok", 2) == 2);
            assert(__xos_file_close(2) == 0 && channel_closes == 2);
        } else {
            if (is("invalid_v3")) { items[2] = {~xos_u32{0}, 1, 2, 7, O_RDWR, 0}; items[3] = {31, 2, 6, 8, O_RDWR, 0}; execution->count = 4; }
            if (is("missing_flag")) { extension->flags = 0; extension->reserved = 0; }
            if (is("missing_object")) execution->count = 0;
            if (is("zero_sequence")) reinterpret_cast<xos::startup_terminal_exec_extension*>(startup_area+176)->next_sequence=0;
            assert(__xos_file_isatty(9) == -EINVAL);
            assert(channel_queries == 0 && channel_closes == 0 && file_sends == 0);
        }
    } else {
        setup();
        if (is("bad_peer")) channels[1].peer_pid = 3;
        if (is("bad_rights")) channels[0].rights = xos::channel_receive;
        if (is("bad_controller")) channels[0].controller_pid = 0;
        if (is("duplicate_channels")) { channels[2] = channels[0]; channels[2].handle = 12; channel_count = 3; }
        if (is("invalid_v2")) reinterpret_cast<xos_file_startup_extension*>(startup_area+64)->flags &= ~1U;
        if (is("bad_peer") || is("bad_rights") || is("bad_controller") || is("duplicate_channels") || is("invalid_v2")) {
            const long expected = is("invalid_v2") || is("bad_controller") ? -EINVAL
                : is("duplicate_channels") ? -EIO : -EACCES;
            assert(__xos_file_isatty(0) == expected && sends == 0 && file_sends == 0);
        } else if (is("lease")) {
            assert(__xos_file_isatty(0) == 1); block_read = true;
            char byte = 0;
            std::thread reader([&] { assert(__xos_file_read(0, &byte, 1) == 1); });
            { std::unique_lock<std::mutex> lock(mock_lock); input_changed.wait(lock, [] { return read_waiting; }); }
            fd_set readable; FD_ZERO(&readable); FD_SET(0,&readable);
            timeval immediate{};
            assert(xos_test_select(1,&readable,nullptr,nullptr,&immediate)==-1 && errno==EBUSY);
            assert(FD_ISSET(0,&readable) && sends == 1);
            assert(__xos_file_close(0) == 0 && __xos_file_close(1) == 0 && __xos_file_close(2) == 0);
            assert(channel_closes == 0);
            const int fd = static_cast<int>(__xos_file_open("/independent", O_RDWR));
            assert(fd == 0 && __xos_file_write(fd, "file", 4) == 4);
            assert(__xos_file_isatty(fd) == -ENOTTY);
            { std::lock_guard<std::mutex> lock(mock_lock); input_ready = true; input_changed.notify_all(); }
            reader.join(); assert(byte == 'R' && channel_closes == 2);
            assert(__xos_file_close(fd) == 0 && file_closes == 1);
        } else if (is("concurrent")) {
            assert(__xos_file_isatty(0) == 1);
            std::thread workers[4];
            for (auto& worker : workers) worker = std::thread([] { for (int n=0;n<100;++n) assert(__xos_file_write(1,"abc",3)==3); });
            for (auto& worker : workers) worker.join();
            assert(sends == 400 && next_sequence == 401 && channel_closes == 0);
        } else if (is("readiness")) {
            assert(__xos_file_isatty(0) == 1);
            fd_set readable;
            FD_ZERO(&readable); FD_SET(0,&readable);
            timeval timeout{2,50};
            readiness_reply = xos::thread_error_timeout;
            assert(xos_test_select(1,&readable,nullptr,nullptr,&timeout) == 0 && !FD_ISSET(0,&readable));
            assert(timeout.tv_sec == 2 && timeout.tv_usec == 50 && pending.deadline_ns == 2000051000);
            readiness_reply = xos::terminal::interrupted;
            FD_SET(0,&readable);
            errno=0;
            assert(xos_test_select(1,&readable,nullptr,nullptr,nullptr) == -1 && errno == EINTR);
            assert(FD_ISSET(0,&readable) && pending.deadline_ns == xos::thread_deadline_infinite);
            readiness_reply = 1;
            timeout = {LONG_MAX,999999};
            assert(xos_test_select(1,&readable,nullptr,nullptr,&timeout) == 1 && FD_ISSET(0,&readable));
            assert(pending.deadline_ns == xos::thread_deadline_infinite-1 && sends == 3 && channel_closes == 0);
        } else if (is("basic")) {
            struct stat info{}; struct termios value{}, original{};
            assert(__xos_file_isatty(0)==1 && __xos_file_isatty(1)==1 && __xos_file_isatty(2)==1);
            assert(__xos_file_stat(0,nullptr,&info)==0 && S_ISCHR(info.st_mode));
            assert(__xos_terminal_tcgetattr(0,&value)==0 && value.c_cflag==(CS8|CREAD|CLOCAL));
            assert(value.c_ispeed==B115200 && value.c_ospeed==B115200 && value.c_cc[VMIN]==1);
            original=value; value.c_lflag=ICANON;
            assert(__xos_terminal_tcsetattr(0,TCSANOW,&value)==-ENOTSUP && sends==1);
            value=original; value.c_cc[VMIN]=0; value.c_cc[VTIME]=1;
            assert(__xos_terminal_tcsetattr(0,TCSAFLUSH,&value)==0 && mode.vtime==1 && pending.deadline_ns==2);
            char byte=0; assert(__xos_file_read(0,&byte,1)==0);
            assert(__xos_terminal_tcdrain(1)==0 && __xos_terminal_tcflush(0,TCIFLUSH)==0);
            const unsigned previous=sends;
            assert(__xos_terminal_tcflush(0,TCOFLUSH)==-ENOTSUP && __xos_terminal_tcflush(0,99)==-EINVAL);
            assert(__xos_terminal_tcsetattr(0,99,&value)==-EINVAL && sends==previous);
            assert(__xos_file_fcntl(0,F_SETFL,O_RDWR|O_NONBLOCK)==-ENOTSUP);
            assert(__xos_file_fcntl(1,F_GETFL,0)==O_RDWR);
            const int alias=static_cast<int>(__xos_file_dup(0,3,0,0)); assert(alias==3);
            assert(xos_test_ioctl(alias,FIOCLEX)==0 && __xos_file_fcntl(alias,F_GETFD,0)==FD_CLOEXEC);
            assert(__xos_file_fcntl(0,F_GETFD,0)==0 && xos_test_ioctl(alias,FIONCLEX)==0);
            errno=0; assert(xos_test_ioctl(alias,0UL)==-1 && errno==ENOTTY);
            assert(xos_test_ioctl(32,FIOCLEX)==-1 && errno==EBADF);
            assert(xos_test_ioctl(alias,TCGETS,&value)==0 && value.c_cc[VTIME]==1);
            assert(__xos_file_write(alias,"12345678901234567890",20)==17);
            for(int fd=0;fd<3;++fd) assert(__xos_file_close(fd)==0);
            assert(channel_closes==0 && __xos_file_close(alias)==0 && channel_closes==2);
        } else {
            struct termios value{}, saved{};
            assert(__xos_file_isatty(0) == 1); fail_once=true;
            long result;
            if (is("zero_write")) result=__xos_file_write(1,"x",1);
            else if (is("overread")) { char byte='?'; result=__xos_file_read(0,&byte,1); assert(byte=='?'); }
            else { std::memset(&value,0xa5,sizeof(value)); saved=value; result=__xos_terminal_tcgetattr(0,&value); assert(!std::memcmp(&saved,&value,sizeof(value))); }
            const long expected=is("interrupted")?-EINTR:is("timeout")?-ETIMEDOUT:is("service_death")?-EACCES:-EIO;
            assert(result==expected);
            if (is("interrupted")) assert(channel_closes==0 && __xos_terminal_tcgetattr(0,&value)==0);
            else { const unsigned count=sends; assert(channel_closes==2 && __xos_file_write(1,"x",1)==-EIO && sends==count); }
        }
    }
    std::printf("PASS glibc_terminal %s\n",argv[1]);
    return 0;
}
