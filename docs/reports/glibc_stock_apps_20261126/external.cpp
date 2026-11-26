// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

int main()
{
    std::vector<std::string> values{"vector"};
    std::thread worker([&values] { values.emplace_back("thread"); });
    worker.join();
    if (values.size() != 2)
        return 2;
    try {
        throw std::runtime_error("exception");
    } catch (const std::runtime_error& error) {
        std::printf("GLIBC_KIT_CPP_OK %s %s %s\n",
                    values[0].c_str(), values[1].c_str(), error.what());
        return 0;
    }
}
