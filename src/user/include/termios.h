/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XOS_TERMIOS_H
#define XOS_TERMIOS_H
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif
typedef uint32_t tcflag_t;
typedef uint32_t speed_t;
typedef uint8_t cc_t;
#define NCCS 16
struct termios {
    tcflag_t c_iflag, c_oflag, c_cflag, c_lflag;
    cc_t c_cc[NCCS];
    speed_t c_ispeed, c_ospeed;
};

#define IGNBRK 0x00000001u
#define BRKINT 0x00000002u
#define IGNPAR 0x00000004u
#define PARMRK 0x00000008u
#define INPCK  0x00000010u
#define ISTRIP 0x00000020u
#define INLCR  0x00000040u
#define IGNCR  0x00000080u
#define ICRNL  0x00000100u
#define IXON   0x00000200u
#define IXOFF  0x00000400u
#define OPOST  0x00000001u
#define ONLCR  0x00000002u
#define CSIZE  0x00000003u
#define CS5    0x00000000u
#define CS6    0x00000001u
#define CS7    0x00000002u
#define CS8    0x00000003u
#define CSTOPB 0x00000004u
#define CREAD  0x00000008u
#define PARENB 0x00000010u
#define PARODD 0x00000020u
#define HUPCL  0x00000040u
#define CLOCAL 0x00000080u
#define ISIG   0x00000001u
#define ICANON 0x00000002u
#define ECHO   0x00000004u
#define ECHOE  0x00000008u
#define ECHOK  0x00000010u
#define ECHONL 0x00000020u
#define NOFLSH 0x00000040u
#define TOSTOP 0x00000080u
#define IEXTEN 0x00000100u
#define VINTR 0
#define VQUIT 1
#define VERASE 2
#define VKILL 3
#define VEOF 4
#define VTIME 5
#define VMIN 6
#define VSTART 7
#define VSTOP 8
#define VSUSP 9
#define VEOL 10
/* Symbolic speed values are available for source compatibility; the current
 * terminal accepts only B115200 and rejects all other requested speeds. */
#define B0 0u
#define B50 50u
#define B75 75u
#define B110 110u
#define B134 134u
#define B150 150u
#define B200 200u
#define B300 300u
#define B600 600u
#define B1200 1200u
#define B1800 1800u
#define B2400 2400u
#define B4800 4800u
#define B9600 9600u
#define B19200 19200u
#define B38400 38400u
#define B115200 115200u
#define TCSANOW 0
#define TCSADRAIN 1
#define TCSAFLUSH 2
#define TCIFLUSH 0
#define TCOFLUSH 1
#define TCIOFLUSH 2

int tcgetattr(int fd, struct termios* value);
int tcsetattr(int fd, int action, const struct termios* value);
int tcflush(int fd, int queue);
int tcdrain(int fd);
speed_t cfgetispeed(const struct termios* value);
speed_t cfgetospeed(const struct termios* value);
int cfsetispeed(struct termios* value, speed_t speed);
int cfsetospeed(struct termios* value, speed_t speed);
void cfmakeraw(struct termios* value);
#ifdef __cplusplus
}
#endif
#endif
