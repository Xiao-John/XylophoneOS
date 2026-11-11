// SPDX-License-Identifier: Apache-2.0
// Retry a provisional capped observation without publishing its partial data.
#pragma once
#include <cstdint>

namespace ssg_watch {
enum class observation_attempt { complete, capped, failed };

template<class attempt_fn,class now_fn,class pause_fn,class on_retry_fn,class on_budget_fn>
bool retry_capped_observation(attempt_fn attempt,now_fn now,pause_fn pause,on_retry_fn on_retry,on_budget_fn on_budget,
                              uint64_t deadline,unsigned &retries){
    constexpr unsigned max_attempts=3;
    constexpr uint64_t retry_pause_ns=10000000ull;
    retries=0;
    for(unsigned index=0;index<max_attempts;++index){
        if(now()>=deadline){on_budget();return false;}
        const auto result=attempt();
        if(result==observation_attempt::complete)return true;
        if(result!=observation_attempt::capped || index+1==max_attempts)return false;
        const auto current=now();
        if(current>=deadline || deadline-current<=retry_pause_ns){on_budget();return false;}
        ++retries;on_retry(retries);pause(current+retry_pause_ns);
    }
    return false;
}
}
