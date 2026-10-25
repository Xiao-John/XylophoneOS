/* SPDX-License-Identifier: Apache-2.0 */
int main(void) {
    volatile unsigned long value = 0;
    for (;;) { ++value; }
}
