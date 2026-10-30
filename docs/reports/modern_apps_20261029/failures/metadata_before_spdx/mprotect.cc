#include <sys/mman.h>
int main(){return mprotect(nullptr,4096,PROT_READ);}
