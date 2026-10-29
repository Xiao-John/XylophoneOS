#include <dlfcn.h>
int main(){return dlopen("x",RTLD_NOW)==nullptr;}
// SPDX-License-Identifier: Apache-2.0
