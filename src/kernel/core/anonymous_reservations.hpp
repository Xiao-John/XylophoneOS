// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/types.hpp>

namespace xos::anonymous_vm {
constexpr u64 arena_begin = 0x100000000000ull;
constexpr u64 arena_end = 0x200000000000ull;
constexpr u64 page = 4096;
constexpr u64 max_alignment = 1ull << 40;
constexpr u64 max_reservation = 4ull << 40;
constexpr u64 max_total = 8ull << 40;
constexpr u32 max_fragments = 256;
constexpr i64 invalid = -1, resources = -4, collision = -7, closing = -8;
struct request {
    u32 version, size, operation, flags;
    u64 address, length, alignment;
    u32 protection, reserved0;
    u64 reserved1, reserved2;
};
static_assert(sizeof(request) == 64);
struct region { u64 begin, end; };

// A bounded, sorted set of uncommitted anonymous intervals. No page-table or
// physical-page allocation is performed. Caller serializes all operations.
class reservations {
    region regions_[max_fragments]{};
    u32 count_ = 0;
    u64 bytes_ = 0;
    static bool aligned(u64 n, u64 a) { return (n & (a - 1)) == 0; }
    static bool interval(u64 address, u64 length) {
        return length != 0 && aligned(address, page) && aligned(length, page) &&
            address >= arena_begin && address < arena_end && length <= arena_end - address;
    }
    static bool valid_reserve(u64 hint, u64 length, u64 alignment, bool exact) {
        return length && aligned(length,page) && length<=max_reservation && alignment>=page &&
            alignment<=max_alignment && !(alignment & (alignment-1)) &&
            (!hint || (aligned(hint,page) && hint>=arena_begin && hint<arena_end)) &&
            (!exact || (hint && aligned(hint,alignment) && interval(hint,length)));
    }
    bool overlaps(u64 begin, u64 end) const {
        for (u32 i=0; i<count_; ++i) {
            if (regions_[i].begin >= end) break;
            if (regions_[i].end > begin) return true;
        }
        return false;
    }
public:
    u32 count() const { return count_; }
    u64 bytes() const { return bytes_; }
    region at(u32 index) const { return index < count_ ? regions_[index] : region{}; }
    void clear() { count_=0; bytes_=0; }
    i64 reserve(u64 hint, u64 length, u64 alignment, bool exact) {
        if (!valid_reserve(hint,length,alignment,exact)) return invalid;
        u64 begin=hint;
        if (!exact && begin) {
            if (begin > arena_end-(alignment-1)) begin=0;
            else begin=(begin+alignment-1)&~(alignment-1);
            if (!begin || !interval(begin,length) || overlaps(begin,begin+length)) begin=0;
        }
        if (!begin) {
            begin=arena_begin;
            for (u32 i=0;i<count_;++i) {
                if (begin <= regions_[i].begin && length <= regions_[i].begin-begin) break;
                if (regions_[i].end>begin) {
                    if (regions_[i].end>arena_end-(alignment-1)) return resources;
                    begin=(regions_[i].end+alignment-1)&~(alignment-1);
                }
            }
            if (!interval(begin,length)) return resources;
        }
        if (overlaps(begin,begin+length)) return exact ? collision : resources;
        if (bytes_>max_total-length) return resources;
        u32 index=0; while(index<count_ && regions_[index].begin<begin) ++index;
        const bool left=index>0 && regions_[index-1].end==begin;
        const bool right=index<count_ && regions_[index].begin==begin+length;
        if (!left && !right && count_==max_fragments) return resources;
        if (left && right) {
            regions_[index-1].end=regions_[index].end;
            for(u32 j=index;j+1<count_;++j) regions_[j]=regions_[j+1];
            --count_;
        } else if(left) regions_[index-1].end=begin+length;
        else if(right) regions_[index].begin=begin;
        else {
            for(u32 j=count_;j>index;--j) regions_[j]=regions_[j-1];
            regions_[index]={begin,begin+length}; ++count_;
        }
        bytes_+=length;
        return static_cast<i64>(begin);
    }
    i64 unmap(u64 begin,u64 length) {
        if(!interval(begin,length)) return invalid;
        const u64 end=begin+length;
        // One interval may split; preflight before modifying anything.
        if(count_==max_fragments) for(u32 i=0;i<count_;++i)
            if(regions_[i].begin<begin && regions_[i].end>end) return resources;
        for(u32 i=0;i<count_;) {
            region& r=regions_[i];
            if(r.begin>=end) break;
            if(r.end<=begin) { ++i; continue; }
            const u64 lo=r.begin>begin?r.begin:begin, hi=r.end<end?r.end:end;
            bytes_-=hi-lo;
            if(lo==r.begin && hi==r.end) {
                for(u32 j=i;j+1<count_;++j) { regions_[j]=regions_[j+1]; }
                --count_;
            } else if(lo==r.begin) { r.begin=hi; ++i; }
            else if(hi==r.end) { r.end=lo; ++i; }
            else {
                const u64 old_end=r.end; r.end=lo;
                for(u32 j=count_;j>i+1;--j) regions_[j]=regions_[j-1];
                regions_[i+1]={hi,old_end}; ++count_; i+=2;
            }
        }
        return 0;
    }
    // Internal wire validator. Capability discovery remains unavailable until
    // VM3 provides lifecycle support; no syscall dispatch is connected here.
    i64 apply(const request& r, bool process_closing) {
        if(r.version!=1 || r.size!=sizeof(request) || r.reserved0 || r.reserved1 || r.reserved2)
            return invalid;
        if(r.operation==1) {
            if((r.flags & ~u32{1}) || r.protection ||
                !valid_reserve(r.address,r.length,r.alignment,(r.flags&1)!=0)) return invalid;
            if(process_closing) return closing;
            return reserve(r.address,r.length,r.alignment,(r.flags&1)!=0);
        }
        if(r.operation==0) {
            if(r.flags || r.address || r.length || r.alignment || r.protection) return invalid;
            return process_closing ? closing : 0;
        }
        if(r.operation==5) {
            if(r.flags || r.alignment || r.protection || !interval(r.address,r.length)) return invalid;
            if(process_closing) return closing;
            return unmap(r.address,r.length);
        }
        return invalid;
    }
};
}
