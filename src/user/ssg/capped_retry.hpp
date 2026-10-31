// SPDX-License-Identifier: Apache-2.0
// Retry a provisional capped observation without publishing its partial data.
#pragma once
#include <cstdint>

namespace ssg_watch {
enum class observation_attempt { complete, capped, failed };

template<class Attempt,class Now,class Pause,class OnRetry,class OnBudget>
bool retry_capped_observation(Attempt attempt,Now now,Pause pause,OnRetry on_retry,OnBudget on_budget,
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
