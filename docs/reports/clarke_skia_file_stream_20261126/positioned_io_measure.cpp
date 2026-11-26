#include "include/core/SkFontMgr.h"
#include "include/core/SkStream.h"
#include "include/core/SkTypeface.h"
#include "include/ports/SkFontMgr_empty.h"
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <sys/stat.h>
#include <unistd.h>

int main(int argc, char** argv)
{
    if (argc != 2)
        return 2;
    auto* file = std::fopen(argv[1], "rb");
    if (!file)
        return 3;
    const int fd = fileno(file);
    struct stat info = {};
    const int stat_status = fstat(fd, &info);
    const int stat_error = stat_status ? errno : 0;
    const int seek = std::fseek(file, 0, SEEK_END);
    const long end = std::ftell(file);
    if (std::fseek(file, 11, SEEK_SET))
        return 4;
    const long start = std::ftell(file);
    std::array<unsigned char, 8192> check{};
    std::array<unsigned char, 8192> single{};
    std::array<unsigned char, 8192> repeat{};
    const auto once = pread(fd, single.data(), single.size(), 31);
    const int once_error = once < 0 ? errno : 0;
    const long after_one = std::ftell(file);
    std::size_t count = 0, calls = 0;
    ssize_t result = 1;
    while (count < repeat.size() && (result = pread(fd, repeat.data() + count, repeat.size() - count, 31 + count)) > 0) {
        ++calls;
        count += result;
    }
    const int repeat_error = result < 0 ? errno : 0;
    const long after_repeat = std::ftell(file);
    if (std::fseek(file, 31, SEEK_SET))
        return 5;
    const auto sequential = std::fread(check.data(), 1, check.size(), file);
    const bool same = count == sequential && count == repeat.size() && std::memcmp(check.data(), repeat.data(), count) == 0;
    const auto eof = pread(fd, single.data(), single.size(), end);
    const auto over = pread(fd, single.data(), single.size(), 0xffffffffUL);
    const int over_error = over < 0 ? errno : 0;
    std::fclose(file);
    auto stream = SkStream::MakeFromFile(argv[1]);
    const size_t length = stream ? stream->getLength() : 0;
    const bool stream_seek = stream && stream->seek(31);
    const size_t stream_count = stream_seek ? stream->read(check.data(), check.size()) : 0;
    auto manager = SkFontMgr_New_Custom_Empty();
    const bool font = bool(manager && manager->makeFromFile(argv[1]));
    std::printf("XOS_SKIA_IO_META fd=%d stat=%d errno=%d size=%ld seek=%d end=%ld\n", fd, stat_status, stat_error, info.st_size, seek, end);
    std::printf("XOS_SKIA_IO_READ once=%zd errno=%d multi=%zu calls=%zu error=%d sequential=%zu equal=%d positions=%ld,%ld,%ld\n",
        once, once_error, count, calls, repeat_error, sequential, same, start, after_one, after_repeat);
    std::printf("XOS_SKIA_IO_SKIA length=%zu seek=%d read=%zu eof=%zd large=%zd large_errno=%d font=%d\n",
        length, stream_seek, stream_count, eof, over, over_error, font);
    return 0;
}
