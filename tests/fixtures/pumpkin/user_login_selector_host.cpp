// SPDX-License-Identifier: Apache-2.0
#include "pumpkin/user_login.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>

int main() {
    using namespace xos;
    using namespace xos::user::pumpkin;
    using anchor_guest::scenario;
    user_login::account_packet selected{};
    selected.op = scenario::user_enroll;
    selected.initialize = 1;
    constexpr char account[] = "initial-owner";
    selected.length = sizeof(account) - 1;
    std::memcpy(selected.name, account, sizeof(account));
    assert(user_login::selected_account(selected, scenario::user_enroll));
    selected.initialize = 0;
    assert(user_login::selected_account(selected, scenario::user_enroll));

    selected.op = scenario::user_login;
    assert(user_login::selected_account(selected, scenario::user_login));
    selected.initialize = 1;
    assert(!user_login::selected_account(selected, scenario::user_login));
    selected.initialize = 0;
    selected.length = name_limit + 1;
    assert(!user_login::selected_account(selected, scenario::user_login));

    user_login::account_packet reserve{};
    reserve.op = scenario::user_enroll;
    reserve.sequence = 2;
    assert(user_login::enrollment_ready(reserve));
    assert(!user_login::selected_account(reserve, scenario::user_enroll));
    reserve.name[0] = 'a';
    assert(!user_login::enrollment_ready(reserve));
    std::puts("PASS operator names and destination reservation use separate bounded, secret-free account frames");
}
