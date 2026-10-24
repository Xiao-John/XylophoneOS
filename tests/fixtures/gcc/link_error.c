/* SPDX-License-Identifier: Apache-2.0 */
extern int deliberately_missing_symbol(void);
int main(void) {
    return deliberately_missing_symbol();
}
