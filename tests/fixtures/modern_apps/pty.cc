#include <pty.h>
int main(){int m,s;return openpty(&m,&s,nullptr,nullptr,nullptr);}
// SPDX-License-Identifier: Apache-2.0
