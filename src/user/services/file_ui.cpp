// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#include <xos/file_ui.hpp>
#include <xos/file_client.hpp>
#include <xos/sdk.hpp>

namespace xos::ui {
namespace {
using namespace xos;
using namespace xos::sdk;

file::Client client;
u8 image_buffer[24576];
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
        print("[edit] buffer retained; old file not truncated\n");
        return;
    }
    dirty = false;
    print("[edit] saved "); print(name); print(" bytes="); decimal(editor_length); print("\n");
}

void editor_help() {
    print("[edit] text lines are stored verbatim; commands start with ':'\n"
          "[edit] :w save  :wq save+quit  :q quit  :q! discard  :p print  :c clear\n");
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
    print("[edit] "); print(name); print(" bytes="); decimal(editor_length);
    print(existed ? " (loaded)\n" : " (new)\n");
    editor_help();
    for (;;) {
        print("| ");
        char line[160]{};
        u32 used = 0;
        bool overflow = false;
        for (;;) {
            char byte = 0;
            const i64 got = read(0, &byte, 1);
            if (got <= 0) { yield(); continue; }
            if (byte == '\r' || byte == '\n') {
                print("\n");
                break;
            }
            if (byte == '\b' || byte == 127) {
                if (used > 0 && !overflow) { --used; print("\b \b"); }
            } else if (byte >= 32 && byte <= 126) {
                if (used + 1 < sizeof(line) && !overflow) {
                    line[used++] = byte;
                    (void)write(1, &byte, 1);
                } else {
                    overflow = true;
                }
            }
        }
        if (overflow) { print("[edit] line too long; discarded\n"); continue; }
        line[used] = '\0';
        if (line[0] == ':') {
            if (equal(line, ":w") || equal(line, ":wq")) {
                save_editor(name, dirty);
                if (equal(line, ":wq") && !dirty) { return; }
            } else if (equal(line, ":q")) {
                if (dirty) { print("[edit] unsaved changes; use :w or :q!\n"); }
                else { return; }
            } else if (equal(line, ":q!")) {
                return;
            } else if (equal(line, ":p")) {
                print_bytes(editor_buffer, editor_length);
                if (editor_length > 0 && editor_buffer[editor_length - 1] != '\n') { print("\n"); }
            } else if (equal(line, ":c")) {
                editor_length = 0;
                dirty = true;
                print("[edit] buffer cleared\n");
            } else if (equal(line, ":help")) {
                editor_help();
            } else {
                print("[edit] unknown command; :help\n");
            }
            continue;
        }
        const u32 needed = used + 1;
        if (editor_length + needed > sizeof(editor_buffer)) {
            print("[edit] buffer full; line rejected, buffer retained\n");
            continue;
        }
        for (u32 i = 0; i < used; ++i) { editor_buffer[editor_length++] = static_cast<u8>(line[i]); }
        editor_buffer[editor_length++] = '\n';
        dirty = true;
    }
}
}

void init() {
    if (!client.init()) {
        print("[files] service unavailable\n");
        return;
    }
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
