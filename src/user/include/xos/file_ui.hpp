#pragma once
#include <xos/abi_types.hpp>

namespace xos::ui {
void init();
bool available();
void list();
void cat(const char* name);
void stat(const char* name);
void remove_file(const char* name);
void edit(const char* name);
void filetest();
i64 load(const char* name, u8* buffer, u32 capacity, u32& length);
i64 sync();
}
