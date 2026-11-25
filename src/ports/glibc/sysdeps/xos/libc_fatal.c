/* SPDX-License-Identifier: Apache-2.0
   Fatal diagnostics cannot acquire allocator, FILE or descriptor locks.  */
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <unistd.h>

static void
raw_write (const char *text, size_t length)
{
  long ignored;
  while (length != 0)
    {
      size_t amount = length > 256 ? 256 : length;
      __asm__ volatile ("int $0x80" : "=a" (ignored)
                        : "a" (1UL), "D" (text), "S" (amount), "d" (0UL)
                        : "memory", "cc");
      if (ignored <= 0 || (size_t) ignored > amount)
        return;
      text += ignored;
      length -= ignored;
    }
}

void
__libc_message_impl (const char *vma_name, const char *format, ...)
{
  (void) vma_name;
  va_list arguments;
  va_start (arguments, format);
  const char *part = format;
  size_t position = 0;
  unsigned int substitutions = 0;
  /* The internal libc message interface accepts %s only.  Bound diagnostic
     reads even when a failure has corrupted the formatting arguments.  */
  while (position < 4096 && format[position] != 0)
    {
      if (format[position] == '%' && format[position + 1] == 's')
        {
          raw_write (part, format + position - part);
          if (substitutions++ == LIBC_MESSAGE_MAX_ARGS)
            break;
          const char *text = va_arg (arguments, const char *);
          if (text == NULL)
            text = "(null)";
          size_t length = 0;
          while (length < 4096 && text[length] != 0)
            ++length;
          raw_write (text, length);
          position += 2;
          part = format + position;
        }
      else
        ++position;
    }
  raw_write (part, format + position - part);
  va_end (arguments);
  _exit (127);
}

void
__libc_fatal (const char *message)
{
  __libc_message_impl ("libc", "%s", message);
}
libc_hidden_def (__libc_fatal)
