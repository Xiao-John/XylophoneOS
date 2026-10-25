// SPDX-License-Identifier: MIT AND Apache-2.0
// Historical MIT base; XOS changes from 2026-10-24 are Apache-2.0.
#pragma once
#include <xos/abi_types.hpp>

namespace xos::ui {
void init();
bool available();
void list(const char* path = "/");
void make_directory(const char* path);
void rename_file(const char* old_path, const char* new_path);
void cat(const char* name);
void stat(const char* name);
bool exists(const char* name);
void remove_file(const char* name);
void edit(const char* name);
void filetest();
i64 load(const char* name, u8* buffer, u32 capacity, u32& length);
i64 sync();
}
