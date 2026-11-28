/* SPDX-License-Identifier: Apache-2.0 */
extern void online_constructor_hold (void) __attribute__ ((weak));
static int constructed;
static void __attribute__ ((constructor)) begin (void)
{
  if (online_constructor_hold) online_constructor_hold ();
  ++constructed;
}
int online_constructors (void) { return constructed; }
