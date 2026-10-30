// SPDX-License-Identifier: Apache-2.0
// Consumer-side continuity checks. This does not prove subtree completeness.
#pragma once
#include <set>
#include <string>

namespace ssg_pipe {
class PageContinuity {
    std::string instance_, epoch_, revision_;
    std::set<std::string> cursors_;
    int scroll_ = 0;
    unsigned pages_ = 0;
    bool closed_ = false;
public:
    bool accept(const std::string &instance, const std::string &epoch,
                const std::string &revision, unsigned sequence, int scroll,
                bool complete, const std::string &cursor) {
        if (closed_ || instance.empty() || epoch.empty() || revision.empty() ||
            sequence != pages_ + 1 || scroll < 0 || scroll > 65536 ||
            (complete ? !cursor.empty() : cursor.empty())) return false;
        if (pages_ && (instance != instance_ || epoch != epoch_ ||
                       revision != revision_ || scroll != scroll_)) return false;
        if (!complete && cursors_.count(cursor)) return false;
        if (!pages_) { instance_ = instance; epoch_ = epoch; revision_ = revision; scroll_ = scroll; }
        if (!complete) cursors_.insert(cursor);
        ++pages_;
        closed_ = complete;
        return true;
    }
};
}
