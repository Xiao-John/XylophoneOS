#!/usr/bin/env python3
import os,sys
p='/Users/perry_guo/Documents/ChatGPT/os/runtime/qemu-prefix/Cellar/qemu/11.1.2/bin/qemu-system-x86_64'
os.execv(p,[p,*sys.argv[1:],"-trace",'events=/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_trace/events,file=/Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-net-clock-irq-repair/build/clock_irq/delivery_trace/pic.log'])
