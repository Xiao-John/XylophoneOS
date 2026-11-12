# SPDX-License-Identifier: Apache-2.0
CC = @cc@
CXX = @cxx@
AR = @ar@
CFLAGS = --sysroot=/sysroot -I/src/sl3
CXXFLAGS = -std=gnu++17 -static --sysroot=/sysroot -I/src/sl3
all: /out/sl3/c.elf /out/sl3/cpp.elf
/out/sl3/project_c.o: /src/sl3/project_c.c /src/sl3/project.h
	$(CC) $(CFLAGS) -c $< -o $@
/out/sl3/project_value.o: /src/sl3/project_value.c /src/sl3/project.h
	$(CC) $(CFLAGS) -c $< -o $@
/out/sl3/libvalue.a: /out/sl3/project_value.o
	$(AR) rcs $@ $<
/out/sl3/c.elf: /out/sl3/project_c.o /out/sl3/libvalue.a
	$(CC) -static --sysroot=/sysroot /out/sl3/project_c.o /out/sl3/libvalue.a -o $@
/out/sl3/project_cpp.o: /src/sl3/project_cpp.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@
/out/sl3/project_cpp_value.o: /src/sl3/project_cpp_value.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@
/out/sl3/cpp.elf: /out/sl3/project_cpp.o /out/sl3/project_cpp_value.o
	$(CXX) -static --sysroot=/sysroot /out/sl3/project_cpp.o /out/sl3/project_cpp_value.o -o $@
