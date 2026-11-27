# SPDX-License-Identifier: Apache-2.0
SHELL := /usr/bin/dash
CC := x86_64-elf-gcc
CXX := x86_64-elf-g++
AR := x86_64-elf-ar
RANLIB := x86_64-elf-ranlib
SRC := /src/native
OUT := /out/native
CFLAGS := -std=gnu11 -O2 --sysroot=/sysroot
CXXFLAGS := -std=gnu++20 -O2 --sysroot=/sysroot
LDFLAGS := -static --sysroot=/sysroot

.PHONY: all
all: $(OUT)/c.elf $(OUT)/cpp.elf
	@printf 'GLIBC_GNU_SEED_MAKE_OK\n';

$(OUT)/project_c.o: $(SRC)/project_c.c $(SRC)/project.h
	$(CC) $(CFLAGS) -c $< -o $@
$(OUT)/project_value.o: $(SRC)/project_value.c $(SRC)/project.h
	$(CC) $(CFLAGS) -c $< -o $@
$(OUT)/libvalue.a: $(OUT)/project_value.o
	$(AR) rc $@ $<
	$(RANLIB) $@
$(OUT)/c.elf: $(OUT)/project_c.o $(OUT)/libvalue.a
	$(CC) $(LDFLAGS) -Wl,-Map,$(OUT)/c.map $^ -o $@
$(OUT)/project_cpp.o: $(SRC)/project_cpp.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@
$(OUT)/project_cpp_value.o: $(SRC)/project_cpp_value.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@
$(OUT)/cpp.elf: $(OUT)/project_cpp.o $(OUT)/project_cpp_value.o
	$(CXX) $(LDFLAGS) -Wl,-Map,$(OUT)/cpp.map $^ -o $@
