# SPDX-License-Identifier: Apache-2.0
CC = /usr/bin/x86_64-elf-gcc
CXX = /usr/bin/x86_64-elf-g++
CFLAGS = --sysroot=/sysroot -I/src/c3demo
OBJS = /out/c3demo/main.o /out/c3demo/value.o /out/c3demo/generated.o
all: /out/c3demo/c.elf /out/c3demo/cpp.elf
/out/c3demo/main.o: /src/c3demo/main.c /src/c3demo/value.h /src/c3demo/generated.h
	@printf 'main\n' >> /out/c3demo/build_count.txt
	$(CC) $(CFLAGS) -c $< -o $@
/out/c3demo/value.o: /src/c3demo/value.c /src/c3demo/value.h
	@printf 'value\n' >> /out/c3demo/build_count.txt
	$(CC) $(CFLAGS) -c $< -o $@
/out/c3demo/generated.o: /src/c3demo/generated.c /src/c3demo/generated.h
	@printf 'generated\n' >> /out/c3demo/build_count.txt
	$(CC) $(CFLAGS) -c $< -o $@
/out/c3demo/c.elf: $(OBJS)
	@printf 'link_c\n' >> /out/c3demo/build_count.txt
	$(CC) --sysroot=/sysroot $(OBJS) -o $@
/out/c3demo/app.o: /src/c3demo/app.cpp /src/c3demo/value.h
	@printf 'cpp\n' >> /out/c3demo/build_count.txt
	$(CXX) -std=gnu++17 -static $(CFLAGS) -c $< -o $@
/out/c3demo/cpp.elf: /out/c3demo/app.o
	@printf 'link_cpp\n' >> /out/c3demo/build_count.txt
	$(CXX) -static --sysroot=/sysroot $< -o $@
