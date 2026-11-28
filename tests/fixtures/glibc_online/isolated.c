/* SPDX-License-Identifier: Apache-2.0 */
extern int online_dep_value (void);
extern int online_dep_step (int);
static int constructed;
static void __attribute__ ((constructor)) begin (void)
{
  ++constructed;
  (void) online_dep_step (1);
}
static void __attribute__ ((destructor)) end (void)
{
  (void) online_dep_step (1);
}
int online_value (void) { return online_dep_value (); }
int online_step (int amount) { return online_dep_step (amount); }
int online_constructors (void) { return constructed; }
