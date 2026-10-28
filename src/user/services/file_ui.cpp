// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/file_ui.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>
#include <xos/text.hpp>

namespace xos::ui {
namespace {
using namespace xos;
using namespace xos::sdk;

file::Client client;
u8 image_buffer[24576];
u8 dash_buffer[file::request_data_size];
u8 editor_buffer[8192];
u32 editor_length;

void print_bytes(const u8* data, u32 length) {
    u32 offset = 0;
    while (offset < length) {
        u32 chunk = length - offset;
        if (chunk > 256) { chunk = 256; }
        const i64 sent = write(1, data + offset, chunk);
        if (sent <= 0) { return; }
        offset += static_cast<u32>(sent);
    }
}

void error_line(const char* operation, i64 result) {
    print("[files] "); print(operation); print(" error="); signed_decimal(result); print("\n");
}

bool read_image(const char* name, u8* buffer, u32 capacity, u32& length) {
    for (u32 id = 1; id < 32; ++id) {
        image_info info{};
        if (syscall(sys_image_info, id, reinterpret_cast<u64>(&info)) < 0) { return false; }
        if (!equal(name, info.name)) { continue; }
        if (info.size > capacity) { return false; }
        image_read_request request{0, reinterpret_cast<u64>(buffer), info.size};
        const i64 result = syscall(sys_image_read, id, reinterpret_cast<u64>(&request));
        if (result != static_cast<i64>(info.size)) { return false; }
        length = static_cast<u32>(info.size);
        return true;
    }
    return false;
}

void save_editor(const char* name, bool& dirty) {
    const i64 result = client.replace(name, editor_buffer, editor_length);
    if (result != 0) {
        error_line("save", result);
        print("[edit] buffer retained; result may be unknown, reread file before retry\n");
        return;
    }
    dirty = false;
    print("[edit] saved "); print(name); print(" bytes="); decimal(editor_length); print("\n");
}

void editor_help() {
    print("[edit] text lines append; :: starts a literal ':' line\n"
          "[edit] :w save  :wq save+quit  :q quit  :q! discard  :p [N [M]] print\n"
          "[edit] :i N insert before  :r N replace  :d N delete  :c clear  :help\n");
}

// A line includes its terminating LF, if present. CR and all other bytes are content.
u32 editor_lines() {
    u32 count = 0;
    for (u32 i = 0; i < editor_length; ++i) {
        if (editor_buffer[i] == '\n') { ++count; }
    }
    if (editor_length && editor_buffer[editor_length - 1] != '\n') { ++count; }
    return count;
}

bool editor_line_range(u32 number, u32& start, u32& end) {
    if (!number) { return false; }
    u32 current = 1;
    start = 0;
    while (start < editor_length && current < number) {
        if (editor_buffer[start++] == '\n') { ++current; }
    }
    if (current != number || start >= editor_length) { return false; }
    end = start;
    while (end < editor_length && editor_buffer[end] != '\n') { ++end; }
    if (end < editor_length) { ++end; }
    return true;
}

// Only safe printable UTF-8 reaches the terminal. Controls and malformed bytes
// are rendered as hexadecimal, never interpreted as terminal commands.
void editor_print_range(u32 start, u32 end) {
    static const char hex[] = "0123456789ABCDEF";
    for (u32 i = start; i < end;) {
        const u8 ch = editor_buffer[i];
        if (ch == '\n') { print("\n"); ++i; continue; }
        xos::text::decoded unit{};
        const auto status = xos::text::decode(reinterpret_cast<const char*>(editor_buffer + i), end - i, unit);
        if (status == xos::text::decode_status::ok && unit.codepoint >= 0x20 &&
            !(unit.codepoint >= 0x7f && unit.codepoint <= 0x9f)) {
            print_bytes(editor_buffer + i, unit.bytes);
            i += unit.bytes;
        } else {
            char escaped[] = {'\\', 'x', hex[ch >> 4], hex[ch & 15]};
            (void)write(1, escaped, sizeof(escaped));
            ++i;
        }
    }
}

bool editor_number(const char*& p, u32& value) {
    while (*p == ' ') { ++p; }
    if (*p < '0' || *p > '9') { return false; }
    value = 0;
    do {
        const u32 digit = static_cast<u32>(*p++ - '0');
        if (value > (0xffffffffu - digit) / 10u) { return false; }
        value = value * 10u + digit;
    } while (*p >= '0' && *p <= '9');
    return true;
}

bool editor_end(const char* p) {
    while (*p == ' ') { ++p; }
    return *p == '\0';
}

// Returns false for an entire rejected input; no caller mutates the buffer.
bool editor_read_line(char* line, u32& used, bool& last_cr) {
    used = 0;
    u32 echoed = 0;
    bool invalid = false;
    bool overflow = false;
    for (;;) {
        char byte = 0;
        const i64 got = read(0, &byte, 1);
        if (got <= 0) { yield(); continue; }
        if (byte == '\n' && last_cr) { last_cr = false; continue; }
        last_cr = byte == '\r';
        if (byte == '\r' || byte == '\n') { print("\n"); break; }
        const u8 value = static_cast<u8>(byte);
        if (value == '\b' || value == 127) {
            if (used && !overflow && !invalid) {
                const auto erased = text::erase_last(line, used);
                used = erased.size;
                if (echoed > used) { echoed = used; }
                for (u32 i = 0; i < erased.columns; ++i) { print("\b \b"); }
            }
        } else if ((value >= 32 && value <= 126) || value >= 0x80) {
            if (used < 159 && !overflow && !invalid) {
                line[used++] = byte;
                text::decoded unit{};
                const auto status = text::decode(line + echoed, used - echoed, unit);
                if (status == text::decode_status::invalid ||
                    (status == text::decode_status::ok && unit.codepoint >= 0x7f && unit.codepoint <= 0x9f)) {
                    invalid = true;
                } else if (status == text::decode_status::ok) {
                    (void)write(1, line + echoed, unit.bytes);
                    echoed += unit.bytes;
                }
            } else { overflow = true; }
        } else { invalid = true; }
    }
    line[used] = '\0';
    if (overflow) { print("[edit] line too long; discarded\n"); return false; }
    if (invalid || !text::valid(line, used)) {
        print("[edit] invalid input; discarded\n"); return false;
    }
    // C1 controls are legal UTF-8 but must not reach the document via input.
    for (u32 i = 0; i < used;) {
        text::decoded unit{};
        (void)text::decode(line + i, used - i, unit);
        if (unit.codepoint >= 0x7f && unit.codepoint <= 0x9f) {
            print("[edit] invalid input; discarded\n"); return false;
        }
        i += unit.bytes;
    }
    return true;
}

bool editor_replace_range(u32 start, u32 end, const char* data, u32 length, bool newline) {
    const u32 removed = end - start;
    const u32 added = length + (newline ? 1u : 0u);
    if (added > sizeof(editor_buffer) - (editor_length - removed)) {
        print("[edit] buffer full; line rejected, buffer retained\n"); return false;
    }
    if (added > removed) {
        for (u32 i = editor_length; i > end; --i) { editor_buffer[i + added - removed - 1] = editor_buffer[i - 1]; }
    } else if (added < removed) {
        for (u32 i = end; i < editor_length; ++i) { editor_buffer[i - removed + added] = editor_buffer[i]; }
    }
    for (u32 i = 0; i < length; ++i) { editor_buffer[start + i] = static_cast<u8>(data[i]); }
    if (newline) { editor_buffer[start + length] = '\n'; }
    editor_length = editor_length - removed + added;
    return true;
}

void run_editor(const char* name) {
    u32 loaded = 0;
    i64 result = client.read_all(name, editor_buffer, sizeof(editor_buffer), loaded);
    if (result != 0) {
        if (result != static_cast<i64>(file::status::not_found)) {
            error_line("open", result);
            return;
        }
        loaded = 0;
    }
    editor_length = loaded;
    const bool existed = result == 0;
    bool dirty = false;
    bool last_cr = false;
    print("[edit] "); print(name); print(" bytes="); decimal(editor_length);
    print(existed ? " (loaded)\n" : " (new)\n");
    editor_help();
    for (;;) {
        print("| ");
        char line[160]{};
        u32 used = 0;
        if (!editor_read_line(line, used, last_cr)) { continue; }
        if (line[0] == ':' && line[1] != ':') {
            if (equal(line, ":w") || equal(line, ":wq")) {
                // A failed save of a clean buffer must not make :wq exit.
                bool save_pending = true;
                save_editor(name, save_pending);
                if (!save_pending) { dirty = false; }
                if (equal(line, ":wq") && !save_pending) { return; }
            } else if (equal(line, ":q")) {
                if (dirty) { print("[edit] unsaved changes; use :w or :q!\n"); }
                else { return; }
            } else if (equal(line, ":q!")) {
                return;
            } else if (line[1] == 'p' && (line[2] == '\0' || line[2] == ' ')) {
                const char* p = line + 2;
                u32 first = 1, last = editor_lines();
                if (!editor_end(p)) {
                    if (!editor_number(p, first)) { print("[edit] invalid range\n"); continue; }
                    last = first;
                    if (!editor_end(p) && !editor_number(p, last)) { print("[edit] invalid range\n"); continue; }
                    if (!editor_end(p) || !first || first > last || last > editor_lines()) {
                        print("[edit] invalid range\n"); continue;
                    }
                }
                if (line[2] == '\0') {
                    editor_print_range(0, editor_length);
                    if (editor_length && editor_buffer[editor_length - 1] != '\n') { print("\n"); }
                } else {
                    for (u32 n = first; n <= last; ++n) {
                        u32 start = 0, end = 0; (void)editor_line_range(n, start, end);
                        decimal(n); print(": "); editor_print_range(start, end);
                        if (end == start || editor_buffer[end - 1] != '\n') { print("\n"); }
                    }
                }
            } else if ((line[1] == 'i' || line[1] == 'r' || line[1] == 'd') && line[2] == ' ') {
                const char operation = line[1];
                const char* p = line + 2;
                u32 number = 0, start = 0, end = 0;
                if (!editor_number(p, number) || !editor_end(p) || !number ||
                    (operation == 'i' && number > editor_lines() + 1) ||
                    (operation != 'i' && !editor_line_range(number, start, end))) {
                    print("[edit] invalid line number\n"); continue;
                }
                if (operation == 'i') {
                    if (number == editor_lines() + 1) { start = end = editor_length; }
                    else { (void)editor_line_range(number, start, end); end = start; }
                }
                if (operation == 'd') {
                    if (editor_replace_range(start, end, "", 0, false)) { dirty = true; }
                    continue;
                }
                print("text| ");
                char replacement[160]{}; u32 length = 0;
                if (!editor_read_line(replacement, length, last_cr)) { continue; }
                const bool terminated = operation == 'i' || (end > start && editor_buffer[end - 1] == '\n');
                // Appending after a non-LF final line needs a separate separator.
                if (operation == 'i' && start == editor_length && editor_length && editor_buffer[editor_length - 1] != '\n') {
                    if (editor_length + 1u + length + 1u > sizeof(editor_buffer)) {
                        print("[edit] buffer full; line rejected, buffer retained\n"); continue;
                    }
                    editor_buffer[editor_length++] = '\n'; ++start; ++end;
                }
                if (editor_replace_range(start, end, replacement, length, terminated)) { dirty = true; }
            } else if (equal(line, ":c")) {
                editor_length = 0; dirty = true; print("[edit] buffer cleared\n");
            } else if (equal(line, ":help")) { editor_help(); }
            else { print("[edit] unknown command; :help\n"); }
            continue;
        }
        const char* content = line;
        if (line[0] == ':' && line[1] == ':') { ++content; --used; }
        const bool separator = editor_length && editor_buffer[editor_length - 1] != '\n';
        if (editor_length + (separator ? 1u : 0u) + used + 1u > sizeof(editor_buffer)) {
            print("[edit] buffer full; line rejected, buffer retained\n"); continue;
        }
        if (separator) { editor_buffer[editor_length++] = '\n'; }
        if (editor_replace_range(editor_length, editor_length, content, used, true)) { dirty = true; }
    }
}
}

void install_boot_dash() {
    const i64 size = syscall(sys_boot_payload, 0, 0, 0);
    if (size <= 0) { return; }
    if (static_cast<u64>(size) > 32ull * 1024 * 1024) {
        print("[files] dash payload too large\n");
        return;
    }
    u32 existing = 0;
    u32 version = 0;
    if (client.stat("/usr/bin/dash", existing, version) == 0) { return; }
    (void)client.mkdir("/usr");
    (void)client.mkdir("/usr/bin");
    i64 result = client.begin_replace("/usr/bin/dash", static_cast<u32>(size));
    if (result != 0) { error_line("dash-stage", result); return; }
    u32 offset = 0;
    while (offset < static_cast<u32>(size)) {
        u32 count = static_cast<u32>(size) - offset;
        if (count > sizeof(dash_buffer)) { count = sizeof(dash_buffer); }
        const i64 copied = syscall(sys_boot_payload, offset,
                                   reinterpret_cast<u64>(dash_buffer), count);
        if (copied != static_cast<i64>(count)) { result = -1; break; }
        result = client.chunk_replace(offset, dash_buffer, count);
        if (result != 0) { break; }
        offset += count;
    }
    if (result == 0) { result = client.commit_replace(); }
    if (result != 0) {
        (void)client.abort_replace();
        error_line("dash-install", result);
        return;
    }
    print("[files] dash installed bytes="); decimal(static_cast<u32>(size)); print("\n");
}

void init() {
    if (!client.init()) {
        print("[files] service unavailable\n");
        return;
    }
    install_boot_dash();
    u32 existing = 0;
    u32 version = 0;
    const i64 stat_result = client.stat("hello.elf", existing, version);
    if (stat_result == 0) {
        print("[files] hello.elf present bytes="); decimal(existing); print("\n");
        return;
    }
    if (stat_result != static_cast<i64>(file::status::not_found)) {
        error_line("bootstrap-stat", stat_result);
        return;
    }
    u32 length = 0;
    if (!read_image("hello", image_buffer, sizeof(image_buffer), length)) {
        print("[files] hello image missing\n");
        return;
    }
    const i64 result = client.replace("hello.elf", image_buffer, length);
    if (result != 0) {
        error_line("bootstrap", result);
        return;
    }
    print("[files] ready hello.elf bytes="); decimal(length); print("\n");
}

bool available() {
    return client.ping() == 0;
}

void list(const char* path) {
    file::entry entries[8]{};
    u32 cursor = 0;
    do {
        u32 count = 0;
        const i64 result = client.list(path, entries, 8, count, cursor);
        if (result != 0) { error_line("list", result); return; }
        for (u32 i = 0; i < count; ++i) {
            print(entries[i].name); if (entries[i].directory) { print("/"); }
            print(" size="); decimal(entries[i].size);
            print(" version="); decimal(entries[i].version); print("\n");
        }
    } while (cursor != 0);
}

void make_directory(const char* path) {
    const i64 result = client.mkdir(path);
    if (result != 0) { error_line("mkdir", result); return; }
    print("[files] directory created "); print(path); print("\n");
}

void rename_file(const char* old_path, const char* new_path) {
    const i64 result = client.rename(old_path, new_path);
    if (result != 0) { error_line("rename", result); return; }
    print("[files] renamed "); print(new_path); print("\n");
}

void cat(const char* name) {
    u32 handle = 0, size = 0, version = 0;
    i64 result = client.open(name, file::read_only, handle, size, version);
    if (result != 0) { error_line("cat", result); return; }
    bool any = false;
    u8 last = 0;
    for (;;) {
        result = client.read(handle, image_buffer, 512);
        if (result <= 0) { break; }
        print_bytes(image_buffer, static_cast<u32>(result));
        last = image_buffer[static_cast<u32>(result) - 1];
        any = true;
    }
    const i64 closed = client.close(handle);
    if (result < 0 || closed < 0) { error_line("cat", result < 0 ? result : closed); return; }
    if (any && last != '\n') { print("\n"); }
}

bool exists(const char* name) {
    u32 size = 0, version = 0;
    return client.stat(name, size, version) == 0;
}

void stat(const char* name) {
    u32 size = 0;
    u32 version = 0;
    const i64 result = client.stat(name, size, version);
    if (result != 0) { error_line("stat", result); return; }
    print(name); print(" size="); decimal(size); print(" version="); decimal(version); print("\n");
}

void remove_file(const char* name) {
    const i64 result = client.remove(name);
    if (result != 0) { error_line("remove", result); return; }
    print("[files] removed "); print(name); print("\n");
}

void edit(const char* name) {
    run_editor(name);
}

i64 load(const char* name, u8* buffer, u32 capacity, u32& length) {
    return client.read_all(name, buffer, capacity, length);
}

i64 sync() {
    return client.sync();
}

void filetest() {
    bool ok = true;
    (void)client.remove("t1");
    const char initial[] = "abcde";
    const i64 replaced = client.replace("t1", initial, 5);
    if (replaced != 0) { print("[filetest] failed stage=1a error="); signed_decimal(replaced); print("\n"); return; }
    u32 h1 = 0, h2 = 0, size = 0, version = 0;
    if (client.open("t1", file::read_only, h1, size, version) != 0 || size != 5) {
        print("[filetest] failed stage=1b size="); decimal(size); print("\n"); return;
    }
    if (client.open("t1", file::read_only, h2, size, version) != 0 || size != 5) {
        print("[filetest] failed stage=1c size="); decimal(size); print("\n"); return;
    }
    char a = 0, b = 0, c = 0;
    const i64 first_read = client.read(h1, &a, 1);
    if (first_read != 1 || a != 'a') {
        print("[filetest] failed stage=1d r="); signed_decimal(first_read);
        print(" char="); if (a >= 32 && a <= 126) { char text[2] = {a, 0}; print(text); }
        print(" h="); decimal(h1); print("\n"); return;
    }
    if (client.read(h2, &b, 1) != 1 || b != 'a') { print("[filetest] failed stage=1e\n"); return; }
    if (client.read(h1, &c, 1) != 1 || c != 'b') { print("[filetest] failed stage=1f\n"); return; }
    if (client.seek(h1, 0) != 0) { print("[filetest] failed stage=1g\n"); return; }
    char short_read[10]{};
    if (client.read(h1, short_read, 10) != 5) { print("[filetest] failed stage=1h\n"); return; }
    if (client.read(h1, short_read, 10) != 0) { print("[filetest] failed stage=1i\n"); return; }
    if (client.seek(h1, 99) != 5 || client.read(h1, short_read, 1) != 0) {
        print("[filetest] failed stage=seek_eof\n"); return;
    }
    if (client.close(h1) != 0 || client.close(h2) != 0) { print("[filetest] failed stage=1j\n"); return; }
    ok = ok && client.open("t1", file::read_write, h1, size, version) == 0;
    ok = ok && client.seek(h1, 5) == 5;
    ok = ok && client.write(h1, "XY", 2) == 2;
    ok = ok && client.close(h1) == 0;
    ok = ok && client.stat("t1", size, version) == 0 && size == 7;
    if (!ok) { print("[filetest] failed stage=2\n"); return; }
    u32 length = 0;
    ok = ok && client.read_all("t1", image_buffer, sizeof(image_buffer), length) == 0 &&
         length == 7 && image_buffer[0] == 'a' && image_buffer[5] == 'X';
    if (!ok) { print("[filetest] failed stage=3\n"); return; }
    // Active readers lock replacement; rejected commit must preserve the file.
    ok = ok && client.open("t1", file::read_only, h1, size, version) == 0;
    ok = ok && client.replace("t1", "bad", 3) < 0;
    ok = ok && client.close(h1) == 0;
    ok = ok && client.stat("t1", size, version) == 0 && size == 7;
    if (!ok) { print("[filetest] failed stage=4\n"); return; }
    char ignored = 0;
    ok = ok && client.read(99, &ignored, 1) < 0;
    ok = ok && client.remove("t1") == 0;
    if (!ok) { print("[filetest] failed stage=6\n"); return; }
    print(ok ? "[filetest] result=pass short=read/eof handles=independent "
               "locked=preserved write=actual invalid=rejected\n"
             : "[filetest] result=FAILED\n");
}
}
