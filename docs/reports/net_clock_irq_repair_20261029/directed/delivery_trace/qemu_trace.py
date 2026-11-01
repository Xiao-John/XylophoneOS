#!/usr/bin/env python3
import os,sys
p='${XOS_WORKTREE_9282C9E77071}/qemu-prefix/Cellar/qemu/11.1.2/bin/qemu-system-x86_64'
os.execv(p,[p,*sys.argv[1:],"-trace",'events=${XOS_WORKTREE_61E12BE2FF84}/build/clock_irq/delivery_trace/events,file=${XOS_WORKTREE_61E12BE2FF84}/build/clock_irq/delivery_trace/pic.log'])
