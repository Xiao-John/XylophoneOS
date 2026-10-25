// SPDX-License-Identifier: Apache-2.0
#ifndef XOS_EDITLINE_READLINE_H
#define XOS_EDITLINE_READLINE_H
char *readline(const char *prompt);
void add_history(const char *line);
#endif
