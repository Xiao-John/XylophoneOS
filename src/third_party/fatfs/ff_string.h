#pragma once
/* Minimal freestanding string runtime used by FatFs. */
#include <stddef.h>

extern "C" {
void* memcpy(void* destination, const void* source, size_t length);
void* memmove(void* destination, const void* source, size_t length);
void* memset(void* destination, int value, size_t length);
int memcmp(const void* left, const void* right, size_t length);
char* strchr(const char* text, int value);
size_t strlen(const char* text);
}
