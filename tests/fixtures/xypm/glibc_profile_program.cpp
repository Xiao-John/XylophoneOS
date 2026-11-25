// SPDX-License-Identifier: Apache-2.0
#include <cstdio>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
thread_local std::string worker_message = "xypm glibc C++ candidate";
std::mutex result_mutex;
int result = 0;
int main() {
  std::vector<std::string> messages{"xypm external glibc C++", "second"};
  std::thread worker([&] {
    std::lock_guard<std::mutex> guard(result_mutex);
    if (!worker_message.empty()) result = messages.size();
  });
  worker.join();
  try { throw std::runtime_error(messages.at(0)); }
  catch (const std::exception& error) { std::puts(error.what()); }
  return result == 2 ? 0 : 1;
}
