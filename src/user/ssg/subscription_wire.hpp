// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <xos/process_abi.hpp>
#include <xos/sdk.hpp>
#include <QtCore/QByteArray>
#include <cstdint>

namespace ssg_subscription {
inline constexpr unsigned protocol_version = 1;
inline constexpr unsigned header_size = 28;
inline constexpr unsigned max_payload_size = xos::process_pipe_bytes - header_size;
inline constexpr unsigned event_kind = 1;
inline constexpr unsigned ack_kind = 2;
inline constexpr unsigned ack_committed = 1;
inline constexpr unsigned ack_rejected = 2;
inline constexpr unsigned browser_slot = 1;
inline constexpr unsigned notes_slot = 2;
inline constexpr char event_magic[4] = {'S', 'G', 'E', 'V'};
inline constexpr char ack_magic[4] = {'S', 'G', 'A', 'K'};

struct frame_header {
    unsigned kind = 0;
    unsigned stream_sequence = 0;
    unsigned payload_size = 0;
    unsigned checksum = 0;
    unsigned source_slot = 0;
};

inline void put_u16(char *out, unsigned value) {
    out[0] = static_cast<char>(value & 0xffu);
    out[1] = static_cast<char>((value >> 8) & 0xffu);
}
inline void put_u32(char *out, unsigned value) {
    for (unsigned i = 0; i < 4; ++i) out[i] = static_cast<char>((value >> (i * 8)) & 0xffu);
}
inline unsigned get_u16(const char *in) {
    return static_cast<unsigned char>(in[0]) |
        (static_cast<unsigned>(static_cast<unsigned char>(in[1])) << 8);
}
inline unsigned get_u32(const char *in) {
    unsigned value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= static_cast<unsigned>(static_cast<unsigned char>(in[i])) << (i * 8);
    return value;
}

// FNV-1a detects accidental payload damage; it is not authentication.
inline unsigned payload_checksum(const char *data, unsigned size) {
    unsigned value = 2166136261u;
    for (unsigned i = 0; i < size; ++i) value = (value ^ static_cast<unsigned char>(data[i])) * 16777619u;
    return value;
}

inline bool encode_frame(char *out, unsigned capacity, unsigned kind, unsigned sequence,
                         unsigned source_slot, const char *payload, unsigned payload_size,
                         unsigned &frame_size) {
    frame_size = 0;
    if (out == nullptr || payload == nullptr || sequence == 0 ||
        payload_size == 0 || payload_size > max_payload_size ||
        capacity < header_size + payload_size ||
        (kind == event_kind && source_slot != browser_slot && source_slot != notes_slot) ||
        (kind == ack_kind && source_slot != 0) || (kind != event_kind && kind != ack_kind)) return false;
    const char *magic = kind == event_kind ? event_magic : ack_magic;
    for (unsigned i = 0; i < 4; ++i) out[i] = magic[i];
    put_u16(out + 4, protocol_version);
    put_u16(out + 6, header_size);
    put_u16(out + 8, kind);
    put_u16(out + 10, 0);
    put_u32(out + 12, sequence);
    put_u32(out + 16, payload_size);
    put_u32(out + 20, payload_checksum(payload, payload_size));
    put_u16(out + 24, source_slot);
    put_u16(out + 26, 0);
    for (unsigned i = 0; i < payload_size; ++i) out[header_size + i] = payload[i];
    frame_size = header_size + payload_size;
    return true;
}

inline bool decode_header(const char *data, unsigned expected_kind, frame_header &out) {
    if (data == nullptr || get_u16(data + 4) != protocol_version ||
        get_u16(data + 6) != header_size || get_u16(data + 8) != expected_kind ||
        get_u16(data + 10) != 0 || get_u16(data + 26) != 0) return false;
    const char *magic = expected_kind == event_kind ? event_magic : ack_magic;
    for (unsigned i = 0; i < 4; ++i) if (data[i] != magic[i]) return false;
    out.kind = get_u16(data + 8);
    out.stream_sequence = get_u32(data + 12);
    out.payload_size = get_u32(data + 16);
    out.checksum = get_u32(data + 20);
    out.source_slot = get_u16(data + 24);
    if (out.stream_sequence == 0 || out.payload_size == 0 || out.payload_size > max_payload_size ||
        (expected_kind == event_kind && out.source_slot != browser_slot && out.source_slot != notes_slot) ||
        (expected_kind == ack_kind && out.source_slot != 0)) return false;
    return true;
}

inline bool verify_payload(const char *data, const frame_header &header) {
    return data != nullptr && payload_checksum(data, header.payload_size) == header.checksum;
}

// Test-build audit only. These records copy the exact framed bytes to the
// diagnostic console; they are not used as transport or as expected answers.
inline bool emit_frame_capture(const char *direction,unsigned sequence,const char *frame,unsigned frame_size,
                               xos::u32 console_handle=1) {
    if(direction==nullptr || frame==nullptr || sequence==0 || frame_size<header_size ||
       frame_size>xos::process_pipe_bytes)return false;
    const auto encoded=QByteArray(frame,static_cast<int>(frame_size)).toBase64();
    auto write_record=[console_handle](const QByteArray &record){
        return !record.isEmpty() && record.size()<=256 &&
            xos::sdk::write(console_handle,record.constData(),static_cast<unsigned>(record.size()))==record.size();
    };
    if(!write_record(QByteArray("P4A_")+direction+"_BEGIN stream="+QByteArray::number(sequence)+
                     " bytes="+QByteArray::number(frame_size)+" encoded="+QByteArray::number(encoded.size())+'\n'))return false;
    for(int offset=0;offset<encoded.size();offset+=96){
        if(!write_record(QByteArray("P4A_")+direction+"_PART stream="+QByteArray::number(sequence)+
                         " offset="+QByteArray::number(offset)+" data="+encoded.mid(offset,96)+'\n'))return false;
    }
    return write_record(QByteArray("P4A_")+direction+"_END stream="+QByteArray::number(sequence)+'\n');
}

inline bool encode_ack(char *out, unsigned capacity, unsigned sequence, unsigned status,
                       unsigned &frame_size) {
    char payload[4];
    put_u32(payload, status);
    return encode_frame(out, capacity, ack_kind, sequence, 0, payload, sizeof(payload), frame_size);
}
}
