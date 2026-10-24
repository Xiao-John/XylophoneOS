/* SPDX-License-Identifier: Apache-2.0 */
/* 128-bit division forces libgcc helpers on x86-64. */
volatile unsigned __int128 numerator = (((unsigned __int128)1) << 100) + 12345;
volatile unsigned __int128 denominator = 17;

int main(void) {
    unsigned __int128 quotient = numerator / denominator;
    unsigned __int128 remainder = numerator % denominator;
    const unsigned __int128 expected =
        (((unsigned __int128)0xf0f0f0f0f0f0f0f0ULL) << 32) | 0xf0f0f3c7U;
    return quotient == expected && remainder == 2 &&
           quotient * denominator + remainder == numerator ? 0 : 1;
}
