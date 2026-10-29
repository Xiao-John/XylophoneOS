// SPDX-License-Identifier: Apache-2.0
int main(int argc,char**){
 if(argc>1){unsigned value=0x80000000u;unsigned short port=0xcf8;__asm__ volatile("outl %0,%1" :: "a"(value),"Nd"(port));}
 else *reinterpret_cast<volatile unsigned*>(0x32000000ull)=0xffffffffu;
 return 0;
}
