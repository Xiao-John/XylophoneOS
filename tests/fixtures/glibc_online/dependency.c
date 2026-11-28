/* SPDX-License-Identifier: Apache-2.0 */
static int state = 100;
int online_dep_value (void) { return state; }
int online_dep_step (int amount) { return state += amount; }
