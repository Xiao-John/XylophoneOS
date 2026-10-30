#include <pty.h>
int main(){int m,s;return openpty(&m,&s,nullptr,nullptr,nullptr);}
