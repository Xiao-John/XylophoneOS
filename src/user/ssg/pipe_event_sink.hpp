// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "subscription_wire.hpp"
#include "watch_service.hpp"
#include <xos/sdk.hpp>
#include <xos/thread_core.hpp>
#include <QtCore/QJsonDocument>
#include <cstdio>

namespace ssg_subscription {
inline constexpr xos::u64 transfer_timeout_ns = 5000000000ull;

class pipe_event_sink final:public ssg_watch::event_sink {
    xos::u32 event_write_;
    xos::u32 ack_read_;
    bool test_full_pipe_=false;
    bool test_corrupt_first_=false;
    unsigned acknowledgements_=0;
    QString failure_;

    enum class io_state { complete, not_sent, incomplete, timeout, error };

    io_state write_frame(const char *frame,unsigned frame_size,xos::u64 deadline) {
        for (;;) {
            const auto result=xos::sdk::syscall(xos::sys_pipe_write,
                xos::u64(event_write_)|xos::pipe_write_atomic_flag,
                reinterpret_cast<xos::u64>(frame),frame_size);
            if (result==static_cast<xos::i64>(frame_size)) return io_state::complete;
            if (result>0) return io_state::incomplete;
            if (result!=xos::process_error_would_block) return io_state::not_sent;
            const auto waited=xos::sdk::syscall(xos::sys_pipe_wait,event_write_,frame_size,deadline);
            if (waited==xos::thread_error_timeout) return io_state::timeout;
            if (waited<0) return io_state::not_sent;
        }
    }

    io_state read_exact(char *data,unsigned length,xos::u64 deadline) {
        unsigned offset=0;
        while (offset<length) {
            const auto result=xos::sdk::syscall(xos::sys_pipe_read,ack_read_,
                reinterpret_cast<xos::u64>(data+offset),length-offset);
            if (result>0) { offset+=static_cast<unsigned>(result);continue; }
            if (result==0) return offset==0?io_state::error:io_state::incomplete;
            if (result!=xos::process_error_would_block) return io_state::error;
            const auto waited=xos::sdk::syscall(xos::sys_pipe_wait,ack_read_,0,deadline);
            if (waited==xos::thread_error_timeout) return io_state::timeout;
            if (waited<0) return io_state::error;
        }
        return io_state::complete;
    }

    ssg_watch::event_delivery fail(ssg_watch::delivery_state state,const QString &reason) {
        failure_=reason;
        return {state,false,reason};
    }

public:
    pipe_event_sink(xos::u32 event_write,xos::u32 ack_read):event_write_(event_write),ack_read_(ack_read){}
    void bind(xos::u32 event_write,xos::u32 ack_read,bool test_full_pipe=false,bool test_corrupt_first=false){
        event_write_=event_write;ack_read_=ack_read;test_full_pipe_=test_full_pipe;test_corrupt_first_=test_corrupt_first;
        acknowledgements_=0;failure_.clear();
    }
    unsigned acknowledgements()const{return acknowledgements_;}
    const QString &failure()const{return failure_;}

    bool begin(const ssg_watch::watch_options &options)override{
        if(!event_write_ || !ack_read_ ||
           xos::sdk::syscall(xos::sys_process_stdio,0,1)!=1)return false;
        std::printf("P4A_SUBSCRIPTION_STARTED protocol=%u interval_s=%u duration_s=%u max_cycles=%u max_unconfirmed=1 replay=NONE globalAtomicSnapshot=NOT_IMPLEMENTED\n",
                    protocol_version,options.interval_seconds,options.duration_seconds,options.max_cycles);
        return std::fflush(stdout)==0;
    }

    ssg_watch::event_delivery publish(const QJsonObject &event,unsigned sequence)override{
        auto payload=QJsonDocument(event).toJson(QJsonDocument::Compact);
        if(payload.isEmpty() || static_cast<unsigned>(payload.size())>max_payload_size)
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("EVENT_FRAME_LIMIT"));
        const auto summary=event.value(QStringLiteral("summary")).toObject();
        const auto summary_bytes=QJsonDocument(summary).toJson(QJsonDocument::Compact).size();
        if(summary.size()>16 || summary_bytes>512)
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("EVENT_SUMMARY_LIMIT"));
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
        if(test_full_pipe_ && sequence==1){
            payload.append(QByteArray(static_cast<int>(max_payload_size)-payload.size(),' '));
        }
#else
        if(test_full_pipe_ || test_corrupt_first_)
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("TEST_MODE_UNAVAILABLE"));
#endif
        unsigned source_slot=0;
        const auto slot=event.value(QStringLiteral("slot")).toString();
        if(slot==QStringLiteral("browser"))source_slot=browser_slot;
        else if(slot==QStringLiteral("notes"))source_slot=notes_slot;
        char frame[xos::process_pipe_bytes]{};unsigned frame_size=0;
        if(!encode_frame(frame,sizeof(frame),event_kind,sequence,source_slot,
                         payload.constData(),static_cast<unsigned>(payload.size()),frame_size))
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("EVENT_FRAME_INVALID"));
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
        if(test_corrupt_first_ && sequence==1)frame[20]=char(static_cast<unsigned char>(frame[20])^1u);
        if(!emit_frame_capture("TX",sequence,frame,frame_size))
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("TX_CAPTURE_FAILED"));
#endif
        const auto deadline=xos::thread::clock()+transfer_timeout_ns;
        const auto written=write_frame(frame,frame_size,deadline);
        if(written==io_state::timeout)
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("EVENT_PIPE_TIMEOUT_BEFORE_WRITE"));
        if(written==io_state::not_sent)
            return fail(ssg_watch::delivery_state::not_sent,QStringLiteral("EVENT_PIPE_CLOSED_OR_ERROR"));
        if(written!=io_state::complete)
            return fail(ssg_watch::delivery_state::unknown,QStringLiteral("EVENT_WRITE_PARTIAL_UNKNOWN"));
        std::printf("P4A_SEND stream=%u slot=%s bytes=%u frame_hash=%08x\n",sequence,
                    slot.toUtf8().constData(),frame_size,payload_checksum(frame,frame_size));
#ifdef XOS_SSG_P3B_TEST_DIAGNOSTICS
        if(test_full_pipe_ && sequence==1){
            const char probe='P';
            const auto probe_result=xos::sdk::syscall(xos::sys_pipe_write,
                xos::u64(event_write_)|xos::pipe_write_atomic_flag,
                reinterpret_cast<xos::u64>(&probe),1);
            const bool full=probe_result==xos::process_error_would_block;
            std::printf("P4A_BACKPRESSURE_PROBE result=%s frame_bytes=%u atomic=1\n",
                        full?"WOULD_BLOCK":"UNEXPECTED",frame_size);
            if(!full)return fail(ssg_watch::delivery_state::unknown,QStringLiteral("PIPE_FULL_EXPECTATION_FAILED"));
        }
#endif

        char ack_header[header_size]{};
        const auto header_read=read_exact(ack_header,sizeof(ack_header),deadline);
        if(header_read!=io_state::complete)
            return fail(ssg_watch::delivery_state::unknown,
                        header_read==io_state::timeout?QStringLiteral("ACK_TIMEOUT_UNKNOWN"):QStringLiteral("ACK_PIPE_CLOSED_OR_TRUNCATED"));
        frame_header decoded{};
        const bool ack_header_valid=decode_header(ack_header,ack_kind,decoded);
        if(!ack_header_valid || decoded.stream_sequence!=sequence || decoded.payload_size!=4 || decoded.source_slot!=0){
            std::printf("P4A_ACK_HEADER stream=%u magic=%02x%02x%02x%02x version=%u size=%u kind=%u flags=%u ack_stream=%u payload=%u slot=%u reserved=%u valid=%d\n",
                        sequence,static_cast<unsigned char>(ack_header[0]),static_cast<unsigned char>(ack_header[1]),
                        static_cast<unsigned char>(ack_header[2]),static_cast<unsigned char>(ack_header[3]),
                        get_u16(ack_header+4),get_u16(ack_header+6),get_u16(ack_header+8),get_u16(ack_header+10),
                        get_u32(ack_header+12),get_u32(ack_header+16),get_u16(ack_header+24),get_u16(ack_header+26),
                        int(ack_header_valid));
            std::fflush(stdout);
            return fail(ssg_watch::delivery_state::unknown,QStringLiteral("ACK_FRAME_MISMATCH_UNKNOWN"));
        }
        char ack_payload[4]{};
        const auto payload_read=read_exact(ack_payload,sizeof(ack_payload),deadline);
        if(payload_read!=io_state::complete || !verify_payload(ack_payload,decoded))
            return fail(ssg_watch::delivery_state::unknown,QStringLiteral("ACK_PAYLOAD_UNKNOWN"));
        const auto status=get_u32(ack_payload);
        if(status==ack_rejected){
            std::printf("P4A_ACK stream=%u status=REJECTED proof=NOT_COMMITTED\n",sequence);
            return fail(ssg_watch::delivery_state::rejected,QStringLiteral("SUBSCRIBER_REJECTED_EVENT"));
        }
        if(status!=ack_committed)
            return fail(ssg_watch::delivery_state::unknown,QStringLiteral("ACK_STATUS_UNKNOWN"));
        ++acknowledgements_;
        std::printf("P4A_ACK stream=%u status=COMMITTED proof=SUBSCRIBER_IN_MEMORY_STATE_ONLY\n",sequence);
        return {ssg_watch::delivery_state::committed,true,{}};
    }

    bool cycle_complete(unsigned cycle,bool partial)override{
        std::printf("P4A_CYCLE_READY cycle=%u aggregate=%s\n",cycle,partial?"PARTIAL":"OBSERVED_COMPLETE");
        return std::fflush(stdout)==0;
    }
};
}
