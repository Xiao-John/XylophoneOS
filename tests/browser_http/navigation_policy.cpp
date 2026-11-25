// SPDX-License-Identifier: Apache-2.0
#include "../../src/ports/aurora_browser/network_policy.hpp"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main() {
    using browser_http::error;
    browser_http::url page{}, target{};
    const char* source = "http://10.0.2.2:8000/web/a.html";
    assert(browser::remote_location(source, strlen(source), nullptr, false, page) == error::ok);
    assert(browser::remote_location("../theme.css", 12, &page, true, target) == error::ok);
    assert(!strcmp(target.target, "/theme.css") && browser::same_origin(page, target));
    assert(browser::remote_location("?v=2#part", 9, &page, true, target) == error::ok);
    assert(!strcmp(target.target, "/web/a.html?v=2"));
    const char* denied[] = {"file:/web/start.html", "https://10.0.2.2/a", "http://10.0.2.3/a",
                            "http://10.0.2.2:8001/a", "//10.0.2.3/a", "javascript:alert(1)"};
    for (const char* item : denied)
        assert(browser::remote_location(item, strlen(item), &page, true, target) != error::ok);
    const char* other = "http://10.0.2.3/a";
    assert(browser::remote_location(other, strlen(other), &page, false, target) == error::ok);
    browser_http::url foreign_base = target;
    assert(browser::remote_resource_location("theme.css", 9, page, foreign_base, target) == error::unsupported);
    assert(browser::remote_resource_location("theme.css", 9, page, page, target) == error::ok);
    assert(browser::remote_resource_location(other, strlen(other), page, page, target) == error::unsupported);
    const char* bad_hosts[] = {"example.test", "010.0.2.2", "1.2.3", "1.2.3.256", "1.2.3.4.5", "", ".1.2.3", "0x7f.0.0.1"};
    for (const char* item : bad_hosts) assert(!browser::numeric_host(item));
    assert(browser::numeric_host("10.0.2.2") && browser::numeric_host("255.255.255.255"));
    char display[browser_http::max_url + 1]{};
    assert(browser::format_location(page, display, sizeof(display)) && !strcmp(display, source));
    assert(!browser::format_location(page, display, 8));
    target = page;
    memset(target.target, 'x', sizeof(target.target));
    assert(!browser::format_location(target, display, sizeof(display)));
    browser::navigation_budget budget;
    assert(!budget.begin(-1) && !budget.request(0));
    assert(!budget.begin(INT64_MAX));
    assert(budget.begin(100));
    const auto deadline = budget.deadline;
    for (unsigned i = 0; i < budget.request_limit; ++i) assert(budget.request(101));
    assert(!budget.request(101) && budget.deadline == deadline);
    assert(budget.begin(100) && !budget.request(static_cast<int64_t>(budget.deadline)));
    assert(budget.begin(100) && !budget.request(-1));
    assert(budget.consume(budget.byte_limit - 1));
    assert(!budget.consume(2) && budget.remaining_bytes() == 1);
    assert(budget.consume(1) && !budget.request(101));
    assert(budget.begin(100) && !budget.consume(SIZE_MAX));
    puts("BROWSER_NETWORK_POLICY_PASS origins=9 hosts=8 budgets=deadline,requests,bytes");
}
