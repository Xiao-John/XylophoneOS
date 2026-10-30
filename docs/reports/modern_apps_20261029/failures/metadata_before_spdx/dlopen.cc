#include <dlfcn.h>
int main(){return dlopen("x",RTLD_NOW)==nullptr;}
