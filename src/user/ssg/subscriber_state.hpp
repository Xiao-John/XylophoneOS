// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "subscription_wire.hpp"
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonObject>
#include <QtCore/QJsonParseError>
#include <QtCore/QStringList>

namespace ssg_subscription {
struct source_state {
    QString slot;
    QString instance;
    QString epoch;
    QString revision;
    QString scope;
    QString state = QStringLiteral("UNKNOWN");
    QString completeness = QStringLiteral("NOT_OBSERVED");
    QString freshness = QStringLiteral("NOT_CURRENT");
    QString last_failure;
    QString last_event_type;
    QJsonObject last_valid_summary;
    unsigned local_sequence = 0;
    bool continuity_valid = false;
};

class consumer_state {
    source_state sources_[2];
    unsigned stream_sequence_ = 0;
    QString error_;

    static bool bounded_string(const QJsonObject &object, const char *key, int maximum,
                               QString &value, bool allow_empty = false) {
        const auto item = object.value(QLatin1String(key));
        if (!item.isString()) return false;
        value = item.toString();
        return value.size() <= maximum && (allow_empty || !value.isEmpty());
    }
    static bool decimal_sequence(const QString &value, unsigned &number) {
        if (value.isEmpty() || value.size() > 10) return false;
        unsigned parsed = 0;
        for (const auto character : value) {
            if (character < QLatin1Char('0') || character > QLatin1Char('9')) return false;
            const unsigned digit = static_cast<unsigned>(character.unicode() - QLatin1Char('0').unicode());
            if (parsed > (0xffffffffu - digit) / 10u) return false;
            parsed = parsed * 10u + digit;
        }
        if (parsed == 0) return false;
        number = parsed;
        return true;
    }
    static bool valid_summary(const QJsonObject &summary) {
        if (summary.size() > 16 || QJsonDocument(summary).toJson(QJsonDocument::Compact).size() > 512) return false;
        for (auto it = summary.begin(); it != summary.end(); ++it) {
            if (it.key().isEmpty() || it.key().size() > 64) return false;
            const auto value = it.value();
            if (value.isString()) { if (value.toString().size() > 128) return false; }
            else if (!value.isBool() && !value.isDouble() && !value.isNull()) return false;
        }
        return true;
    }
    static bool valid_clock(const QJsonObject &event) {
        const auto start = event.value(QStringLiteral("observation_start"));
        const auto end = event.value(QStringLiteral("observation_end"));
        if (start.isNull() && end.isNull()) return true;
        if (!start.isString() || !end.isString()) return false;
        bool start_ok = false, end_ok = false;
        const auto start_ns = start.toString().toULongLong(&start_ok, 10);
        const auto end_ns = end.toString().toULongLong(&end_ok, 10);
        return start_ok && end_ok && end_ns >= start_ns;
    }
    void invalidate_all(const QString &reason) {
        for (auto &source : sources_) {
            source.continuity_valid = false;
            source.state = QStringLiteral("RESET_REQUIRED");
            source.last_failure = reason;
            source.last_valid_summary = {};
        }
    }
    bool reject(const QString &reason) {
        error_ = reason;
        invalidate_all(reason);
        return false;
    }

public:
    consumer_state(const QString &browser_instance, const QString &notes_instance) {
        sources_[0].slot = QStringLiteral("browser");
        sources_[0].instance = browser_instance;
        sources_[1].slot = QStringLiteral("notes");
        sources_[1].instance = notes_instance;
    }

    const source_state &source(unsigned slot) const {
        return sources_[slot == browser_slot ? 0 : 1];
    }
    unsigned stream_sequence() const { return stream_sequence_; }
    const QString &error() const { return error_; }
    void require_resync(const QString &reason) { invalidate_all(reason);error_=reason; }

    bool accept(unsigned header_slot, unsigned stream_sequence, const char *payload, unsigned payload_size) {
        error_.clear();
        if (stream_sequence != stream_sequence_ + 1 || stream_sequence == 0)
            return reject(QStringLiteral("STREAM_SEQUENCE_DISCONTINUITY"));
        if (header_slot != browser_slot && header_slot != notes_slot)
            return reject(QStringLiteral("SOURCE_SLOT_INVALID"));
        if (payload == nullptr || payload_size == 0 || payload_size > max_payload_size)
            return reject(QStringLiteral("PAYLOAD_LENGTH_INVALID"));
        QJsonParseError parse_error{};
        const auto document = QJsonDocument::fromJson(QByteArray(payload, static_cast<int>(payload_size)), &parse_error);
        if (parse_error.error != QJsonParseError::NoError || !document.isObject())
            return reject(QStringLiteral("EVENT_JSON_INVALID"));
        const auto event = document.object();
        static const QStringList fields{
            QStringLiteral("slot"), QStringLiteral("identity_namespace"),
            QStringLiteral("source_instance"), QStringLiteral("source_epoch"),
            QStringLiteral("source_revision_before"), QStringLiteral("source_revision_after"),
            QStringLiteral("sequence"), QStringLiteral("observation_start"),
            QStringLiteral("observation_end"), QStringLiteral("observation_scope"),
            QStringLiteral("presentation_state"), QStringLiteral("capability_set"),
            QStringLiteral("event_type"), QStringLiteral("retry_count"),
            QStringLiteral("completeness"), QStringLiteral("freshness"),
            QStringLiteral("failure_reason"), QStringLiteral("summary"),
            QStringLiteral("baseline_state")};
        if (event.size() != fields.size()) return reject(QStringLiteral("EVENT_FIELD_SET_INVALID"));
        for (const auto &field : fields) if (!event.contains(field)) return reject(QStringLiteral("EVENT_FIELD_MISSING"));

        QString slot_name, instance, epoch, revision_before, revision_after, local_sequence_text;
        QString scope, presentation, event_type, completeness, freshness, failure, baseline_state;
        if (!bounded_string(event, "slot", 16, slot_name) ||
            !bounded_string(event, "source_instance", 64, instance) ||
            !bounded_string(event, "source_epoch", 64, epoch, true) ||
            !bounded_string(event, "source_revision_before", 64, revision_before, true) ||
            !bounded_string(event, "source_revision_after", 64, revision_after, true) ||
            !bounded_string(event, "sequence", 10, local_sequence_text) ||
            !bounded_string(event, "observation_scope", 64, scope) ||
            !bounded_string(event, "presentation_state", 64, presentation) ||
            !bounded_string(event, "event_type", 32, event_type) ||
            !bounded_string(event, "completeness", 64, completeness) ||
            !bounded_string(event, "freshness", 64, freshness) ||
            !bounded_string(event, "failure_reason", 128, failure, true) ||
            !bounded_string(event, "baseline_state", 32, baseline_state) ||
            !valid_clock(event) || !event.value(QStringLiteral("capability_set")).isObject() ||
            !event.value(QStringLiteral("summary")).isObject() ||
            !valid_summary(event.value(QStringLiteral("summary")).toObject()))
            return reject(QStringLiteral("EVENT_VALUE_INVALID"));

        const unsigned index = header_slot == browser_slot ? 0u : 1u;
        auto &current = sources_[index];
        const auto namespace_object = event.value(QStringLiteral("identity_namespace")).toObject();
        if (slot_name != current.slot || instance != current.instance ||
            namespace_object.size() != 3 ||
            namespace_object.value(QStringLiteral("slot")).toString() != slot_name ||
            namespace_object.value(QStringLiteral("source_instance")).toString() != instance ||
            namespace_object.value(QStringLiteral("source_epoch")).toString() != epoch)
            return reject(QStringLiteral("SOURCE_IDENTITY_MISMATCH"));

        unsigned local_sequence = 0;
        if (!decimal_sequence(local_sequence_text, local_sequence) ||
            local_sequence != current.local_sequence + 1)
            return reject(QStringLiteral("SOURCE_SEQUENCE_DISCONTINUITY"));
        const auto capabilities = event.value(QStringLiteral("capability_set")).toObject();
        if (capabilities.isEmpty() || capabilities.size() > 16 ||
            event.value(QStringLiteral("retry_count")).toInt(-1) < 0 ||
            event.value(QStringLiteral("retry_count")).toInt(-1) > 32)
            return reject(QStringLiteral("OBSERVATION_METADATA_INVALID"));

        const bool has_current_observation = baseline_state == QStringLiteral("CURRENT_OBSERVATION") &&
            completeness != QStringLiteral("NOT_OBSERVED") && freshness != QStringLiteral("NOT_CURRENT") &&
            !epoch.isEmpty() && !revision_after.isEmpty();
        if (baseline_state != QStringLiteral("CURRENT_OBSERVATION") &&
            baseline_state != QStringLiteral("HISTORICAL_OR_ABSENT"))
            return reject(QStringLiteral("BASELINE_STATE_INVALID"));
        static const QStringList event_types{
            QStringLiteral("SOURCE_CHANGED"), QStringLiteral("SOURCE_UNCHANGED"),
            QStringLiteral("RESET_REQUIRED"), QStringLiteral("SOURCE_UNKNOWN"),
            QStringLiteral("SOURCE_REPLACED"), QStringLiteral("SOURCE_UNAVAILABLE"),
            QStringLiteral("SOURCE_INVALIDATED"), QStringLiteral("PERMISSION_CHANGED")};
        if (!event_types.contains(event_type)) return reject(QStringLiteral("EVENT_TYPE_INVALID"));
        if (current.local_sequence != 0 && current.epoch != epoch &&
            event_type != QStringLiteral("SOURCE_REPLACED") &&
            event_type != QStringLiteral("RESET_REQUIRED") &&
            event_type != QStringLiteral("SOURCE_UNKNOWN") &&
            event_type != QStringLiteral("SOURCE_UNAVAILABLE") &&
            event_type != QStringLiteral("SOURCE_INVALIDATED") &&
            event_type != QStringLiteral("PERMISSION_CHANGED"))
            return reject(QStringLiteral("EPOCH_CHANGED_WITHOUT_RESET"));
        if ((event_type == QStringLiteral("SOURCE_CHANGED") || event_type == QStringLiteral("SOURCE_UNCHANGED")) &&
            (!current.continuity_valid || current.epoch != epoch || current.scope != scope ||
             current.revision != revision_before || !has_current_observation))
            return reject(QStringLiteral("CHANGE_WITHOUT_CONTIGUOUS_BASELINE"));
        if ((event_type == QStringLiteral("SOURCE_UNAVAILABLE") ||
             event_type == QStringLiteral("SOURCE_INVALIDATED")) && has_current_observation)
            return reject(QStringLiteral("INVALIDATION_PUBLISHED_AS_CURRENT"));

        current.local_sequence = local_sequence;
        current.epoch = epoch;
        current.revision = revision_after;
        current.scope = scope;
        current.completeness = completeness;
        current.freshness = freshness;
        current.last_failure = failure;
        current.last_event_type = event_type;
        if (failure == QStringLiteral("DENIED")) {
            current.state = QStringLiteral("DENIED");
            current.continuity_valid = false;
            current.last_valid_summary = {};
        } else if (failure == QStringLiteral("PROTECTED")) {
            current.state = QStringLiteral("PROTECTED");
            current.continuity_valid = false;
            current.last_valid_summary = {};
        } else if (event_type == QStringLiteral("PERMISSION_CHANGED") && has_current_observation) {
            current.state = QStringLiteral("RESET_REQUIRED");
            current.continuity_valid = true;
            current.last_valid_summary = event.value(QStringLiteral("summary")).toObject();
        } else if (event_type == QStringLiteral("PERMISSION_CHANGED")) {
            current.state = QStringLiteral("DENIED");
            current.continuity_valid = false;
            current.last_valid_summary = {};
        } else if (event_type == QStringLiteral("SOURCE_UNAVAILABLE")) {
            current.state = QStringLiteral("UNAVAILABLE");
            current.continuity_valid = false;
            current.last_valid_summary = {};
        } else if (event_type == QStringLiteral("SOURCE_INVALIDATED")) {
            current.state = QStringLiteral("RESET_REQUIRED");
            current.continuity_valid = false;
            current.last_valid_summary = {};
        } else if (has_current_observation) {
            current.continuity_valid = true;
            current.last_valid_summary = event.value(QStringLiteral("summary")).toObject();
            if (event_type == QStringLiteral("SOURCE_CHANGED")) current.state = QStringLiteral("CHANGED");
            else if (event_type == QStringLiteral("SOURCE_UNCHANGED")) current.state = QStringLiteral("UNCHANGED");
            else if (event_type == QStringLiteral("SOURCE_REPLACED")) current.state = QStringLiteral("REPLACED");
            else if (event_type == QStringLiteral("RESET_REQUIRED")) current.state = QStringLiteral("RESET_REQUIRED");
            else current.state = QStringLiteral("OBSERVED");
        } else {
            current.continuity_valid = false;
            current.last_valid_summary = {};
            current.state = QStringLiteral("UNKNOWN");
        }
        stream_sequence_ = stream_sequence;
        return true;
    }
};
}
