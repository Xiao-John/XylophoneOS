// SPDX-License-Identifier: Apache-2.0
// Guest-side directed checks for the independent Subscriber continuity model.
#include "../../../src/user/ssg/subscriber_state.hpp"
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <cstdio>
#include <cstring>

using namespace ssg_subscription;
namespace {
unsigned checks=0,failures=0;
void check(bool condition,const char *name){
    ++checks;
    std::printf("P4A_STATE_CHECK %s=%s\n",name,condition?"PASS":"FAIL");
    if(!condition)++failures;
}
QJsonObject make_event(const QString &slot,const QString &instance,const QString &epoch,
                       unsigned local_sequence,const QString &event_type,
                       const QString &before,const QString &after,
                       const QString &baseline,const QString &failure={},
                       const QJsonObject &summary={}){
    const QJsonObject identity{{"slot",slot},{"source_instance",instance},{"source_epoch",epoch}};
    return {{"slot",slot},{"identity_namespace",identity},{"source_instance",instance},{"source_epoch",epoch},
        {"source_revision_before",before},{"source_revision_after",after},
        {"sequence",QString::number(local_sequence)},
        {"observation_start",QStringLiteral("10")},{"observation_end",QStringLiteral("11")},
        {"observation_scope",slot=="browser"?QStringLiteral("unfiltered-litehtml"):QStringLiteral("document-range-UTF-16")},
        {"presentation_state",QStringLiteral("hidden-test-no-surface-no-input")},
        {"capability_set",QJsonObject{{"structure",QStringLiteral("SUPPORTED")}}},
        {"event_type",event_type},{"retry_count",0},{"completeness",baseline=="CURRENT_OBSERVATION"?QStringLiteral("SCOPED_COMPLETE"):QStringLiteral("NOT_OBSERVED")},
        {"freshness",baseline=="CURRENT_OBSERVATION"?QStringLiteral("OBSERVED_NOW"):QStringLiteral("NOT_CURRENT")},
        {"failure_reason",failure},{"summary",summary},{"baseline_state",baseline}};
}
bool submit(consumer_state &state,unsigned slot,unsigned stream,const QJsonObject &event){
    const auto payload=QJsonDocument(event).toJson(QJsonDocument::Compact);
    return state.accept(slot,stream,payload.constData(),static_cast<unsigned>(payload.size()));
}
}

int main(){
    const QString browser_instance=QString(32,QLatin1Char('b'));
    const QString notes_instance=QString(32,QLatin1Char('n'));
    const QString epoch_one=QStringLiteral("epoch-one");
    consumer_state valid(browser_instance,notes_instance);
    check(submit(valid,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION")) &&
          valid.source(browser_slot).state=="OBSERVED" && valid.source(browser_slot).continuity_valid,
          "initial_browser_baseline");
    check(submit(valid,notes_slot,2,make_event("notes",notes_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION")) &&
          valid.source(notes_slot).state=="OBSERVED" && valid.stream_sequence()==2,
          "initial_notes_baseline");
    check(submit(valid,notes_slot,3,make_event("notes",notes_instance,epoch_one,2,"SOURCE_CHANGED","1","2","CURRENT_OBSERVATION","",{{"text_changed",true},{"revision_changed",true}})) &&
          valid.source(notes_slot).state=="CHANGED" && valid.source(notes_slot).local_sequence==2,
          "contiguous_source_change");

    consumer_state duplicate(browser_instance,notes_instance);
    submit(duplicate,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(!submit(duplicate,browser_slot,1,make_event("browser",browser_instance,epoch_one,2,"SOURCE_CHANGED","1","2","CURRENT_OBSERVATION")) &&
          duplicate.source(browser_slot).state=="RESET_REQUIRED" && duplicate.source(browser_slot).last_valid_summary.isEmpty(),
          "duplicate_stream_sequence_resets_state");

    consumer_state gap(browser_instance,notes_instance);
    submit(gap,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(!submit(gap,browser_slot,3,make_event("browser",browser_instance,epoch_one,2,"SOURCE_CHANGED","1","2","CURRENT_OBSERVATION")) &&
          gap.error()=="STREAM_SEQUENCE_DISCONTINUITY" && !gap.source(browser_slot).continuity_valid,
          "stream_sequence_gap_resets_state");

    consumer_state local_gap(browser_instance,notes_instance);
    submit(local_gap,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(!submit(local_gap,browser_slot,2,make_event("browser",browser_instance,epoch_one,3,"SOURCE_CHANGED","1","2","CURRENT_OBSERVATION")) &&
          local_gap.error()=="SOURCE_SEQUENCE_DISCONTINUITY",
          "source_sequence_gap_rejected");

    consumer_state wrong_slot(browser_instance,notes_instance);
    check(!submit(wrong_slot,notes_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION")) &&
          wrong_slot.error()=="SOURCE_IDENTITY_MISMATCH",
          "wrong_header_source_rejected");

    consumer_state wrong_instance(browser_instance,notes_instance);
    const QString foreign_instance=QString(32,QLatin1Char('x'));
    check(!submit(wrong_instance,browser_slot,1,make_event("browser",foreign_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION")) &&
          wrong_instance.error()=="SOURCE_IDENTITY_MISMATCH",
          "source_instance_replacement_requires_new_session");

    consumer_state wrong_epoch(browser_instance,notes_instance);
    submit(wrong_epoch,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(!submit(wrong_epoch,browser_slot,2,make_event("browser",browser_instance,"epoch-two",2,"SOURCE_UNCHANGED","1","1","CURRENT_OBSERVATION")) &&
          wrong_epoch.error()=="EPOCH_CHANGED_WITHOUT_RESET",
          "epoch_change_requires_replacement_event");

    consumer_state replacement(browser_instance,notes_instance);
    submit(replacement,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(submit(replacement,browser_slot,2,make_event("browser",browser_instance,"epoch-two",2,"SOURCE_REPLACED","1","2","CURRENT_OBSERVATION")) &&
          replacement.source(browser_slot).state=="REPLACED" && replacement.source(browser_slot).continuity_valid,
          "explicit_epoch_replacement_rebaselines");

    consumer_state stale_revision(browser_instance,notes_instance);
    submit(stale_revision,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(!submit(stale_revision,browser_slot,2,make_event("browser",browser_instance,epoch_one,2,"SOURCE_CHANGED","old","2","CURRENT_OBSERVATION")) &&
          stale_revision.error()=="CHANGE_WITHOUT_CONTIGUOUS_BASELINE",
          "stale_revision_change_rejected");

    consumer_state denied(browser_instance,notes_instance);
    submit(denied,notes_slot,1,make_event("notes",notes_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(submit(denied,notes_slot,2,make_event("notes",notes_instance,"",2,"PERMISSION_CHANGED","1","","HISTORICAL_OR_ABSENT","DENIED")) &&
          denied.source(notes_slot).state=="DENIED" && !denied.source(notes_slot).continuity_valid &&
          denied.source(notes_slot).last_valid_summary.isEmpty(),
          "denial_clears_current_summary");

    consumer_state protected_source(browser_instance,notes_instance);
    submit(protected_source,notes_slot,1,make_event("notes",notes_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(submit(protected_source,notes_slot,2,make_event("notes",notes_instance,"",2,"PERMISSION_CHANGED","1","","HISTORICAL_OR_ABSENT","PROTECTED")) &&
          protected_source.source(notes_slot).state=="PROTECTED" && protected_source.source(notes_slot).last_valid_summary.isEmpty(),
          "protection_clears_current_summary");

    consumer_state unavailable(browser_instance,notes_instance);
    submit(unavailable,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION"));
    check(submit(unavailable,browser_slot,2,make_event("browser",browser_instance,"",2,"SOURCE_UNAVAILABLE","1","","HISTORICAL_OR_ABSENT","SOURCE_EXITED")) &&
          unavailable.source(browser_slot).state=="UNAVAILABLE" && unavailable.source(browser_slot).last_valid_summary.isEmpty(),
          "provider_exit_invalidates_current_summary");

    consumer_state extra_field(browser_instance,notes_instance);
    auto with_text=make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION");
    with_text["text"]="application text is not a summary";
    check(!submit(extra_field,browser_slot,1,with_text) && extra_field.error()=="EVENT_FIELD_SET_INVALID",
          "unexpected_content_field_rejected");

    consumer_state large_summary(browser_instance,notes_instance);
    const QJsonObject oversized{{"value",QString(513,QLatin1Char('x'))}};
    check(!submit(large_summary,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"SOURCE_UNKNOWN","","1","CURRENT_OBSERVATION","",oversized)) &&
          large_summary.error()=="EVENT_VALUE_INVALID",
          "oversized_summary_rejected");

    consumer_state unknown_type(browser_instance,notes_instance);
    check(!submit(unknown_type,browser_slot,1,make_event("browser",browser_instance,epoch_one,1,"EXECUTE_ACTION","","1","CURRENT_OBSERVATION")) &&
          unknown_type.error()=="EVENT_TYPE_INVALID",
          "unknown_event_type_rejected");

    const char wire_payload[]="{\"ok\":true}";
    char wire_frame[xos::process_pipe_bytes]{};unsigned wire_size=0;
    check(encode_frame(wire_frame,sizeof(wire_frame),event_kind,1,browser_slot,wire_payload,
                       sizeof(wire_payload)-1,wire_size) && wire_size==header_size+sizeof(wire_payload)-1,
          "wire_event_encode");
    frame_header wire_header{};
    check(decode_header(wire_frame,event_kind,wire_header) &&
          wire_header.source_slot==browser_slot && verify_payload(wire_frame+header_size,wire_header),
          "wire_event_decode_and_checksum");
    char bad_wire[xos::process_pipe_bytes]{};
    std::memcpy(bad_wire,wire_frame,wire_size);put_u16(bad_wire+4,protocol_version+1);
    check(!decode_header(bad_wire,event_kind,wire_header),"unknown_protocol_version_rejected");
    std::memcpy(bad_wire,wire_frame,wire_size);put_u16(bad_wire+24,3);
    check(!decode_header(bad_wire,event_kind,wire_header),"invalid_source_slot_rejected");
    std::memcpy(bad_wire,wire_frame,wire_size);put_u32(bad_wire+16,max_payload_size+1);
    check(!decode_header(bad_wire,event_kind,wire_header),"oversized_frame_length_rejected");
    std::memcpy(bad_wire,wire_frame,wire_size);bad_wire[header_size]^=1;
    check(decode_header(bad_wire,event_kind,wire_header) && !verify_payload(bad_wire+header_size,wire_header),
          "wire_checksum_damage_rejected");
    char full_payload[max_payload_size];
    std::memset(full_payload,' ',sizeof(full_payload));
    check(encode_frame(wire_frame,sizeof(wire_frame),event_kind,2,notes_slot,full_payload,
                       sizeof(full_payload),wire_size) && wire_size==xos::process_pipe_bytes,
          "atomic_pipe_frame_exact_capacity");
    char ack_frame[header_size+4]{};unsigned ack_size=0;
    check(encode_ack(ack_frame,sizeof(ack_frame),7,ack_committed,ack_size) &&
          decode_header(ack_frame,ack_kind,wire_header) && wire_header.stream_sequence==7 &&
          get_u32(ack_frame+header_size)==ack_committed,
          "ack_sequence_and_status_frame");

    std::printf("P4A_STATE_TEST_DONE checks=%u failures=%u\n",checks,failures);
    return failures==0?0:1;
}
