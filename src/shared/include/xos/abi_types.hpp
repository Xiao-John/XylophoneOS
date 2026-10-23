#pragma once
namespace xos {
using u8 = __UINT8_TYPE__;
using u16 = __UINT16_TYPE__;
using u32 = __UINT32_TYPE__;
using u64 = __UINT64_TYPE__;
using usize = __SIZE_TYPE__;
using i32 = __INT32_TYPE__;
using i64 = __INT64_TYPE__;
static_assert(sizeof(u8) == 1 && sizeof(u16) == 2);
static_assert(sizeof(u32) == 4 && sizeof(u64) == 8);
static_assert(sizeof(i32) == 4 && sizeof(i64) == 8);
}
