# SPDX-License-Identifier: Apache-2.0
CC = /usr/bin/x86_64-elf-gcc
CXX = /usr/bin/x86_64-elf-g++
FLAGS = --sysroot=/sysroot -O2 -mno-red-zone -fno-pie -I/xos_sdk/include -I/src/make
OBJECTS = /out/mk_main.o /out/mk_parser.o /out/mk_rules.o /out/mk_defaults.o /out/mk_posix.o
all: /out/make
/out/mk_main.o: /src/make/main.c /src/make/make.h
	$(CC) -std=c11 $(FLAGS) -c $< -o $@
/out/mk_parser.o: /src/make/parser.c /src/make/make.h
	$(CC) -std=c11 $(FLAGS) -c $< -o $@
/out/mk_rules.o: /src/make/rules.c /src/make/make.h
	$(CC) -std=c11 $(FLAGS) -c $< -o $@
/out/mk_defaults.o: /src/make/defaults.c /src/make/make.h
	$(CC) -std=c11 $(FLAGS) -c $< -o $@
/out/mk_posix.o: /src/make/posix_xos.cpp /src/make/make.h
	$(CXX) -std=c++17 $(FLAGS) -fno-exceptions -fno-rtti -c $< -o $@
/out/make: $(OBJECTS)
	$(CC) -specs=/tests/C3Self.specs -static $(OBJECTS) -o $@
