// SPDX-License-Identifier: Apache-2.0
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "quickjs.h"
static unsigned ticks;
static JSValue rejected[128];
static unsigned active[128];
static int rejected_overflow;
static void rejection(JSContext *ctx, JSValueConst promise, JSValueConst reason, int handled, void *opaque) {
    (void)reason; (void)opaque;
    for (unsigned i=0;i<128;i++) {
        if(active[i] && JS_VALUE_GET_PTR(rejected[i])==JS_VALUE_GET_PTR(promise)) {
            if(handled){JS_FreeValue(ctx,rejected[i]);active[i]=0;}return;
        }
    }
    if(handled)return;
    for(unsigned i=0;i<128;i++)if(!active[i]){rejected[i]=JS_DupValue(ctx,promise);active[i]=1;return;}
    rejected_overflow=1;
}
static int stop(JSRuntime *rt, void *opaque) { (void)rt; (void)opaque; return ++ticks > 1000; }
static void exception(JSContext *ctx) {
    JSValue e = JS_GetException(ctx);
    const char *s = JS_ToCString(ctx, e);
    fprintf(stderr, "JS_EXCEPTION:%s\n", s ? s : "unknown");
    JS_FreeCString(ctx,s); JS_FreeValue(ctx,e);
}
int main(int argc,char **argv) {
    if(argc!=2)return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 3;
    char *source=malloc(262145);if(!source){fclose(f);return 4;}
    size_t n=fread(source,1,262145,f);int io=ferror(f);fclose(f);
    if(io||n>262144){free(source);return 5;}source[n]=0;
    JSRuntime *rt=JS_NewRuntime();if(!rt){free(source);return 6;}
    JS_SetHostPromiseRejectionTracker(rt,rejection,NULL);JS_SetMemoryLimit(rt,16*1024*1024);JS_SetMaxStackSize(rt,64*1024);JS_SetInterruptHandler(rt,stop,NULL);
    JSContext *ctx=JS_NewContext(rt);if(!ctx){JS_FreeRuntime(rt);free(source);return 7;}
    JSValue value=JS_Eval(ctx,source,n,argv[1],(strstr(argv[1],".mjs") ? JS_EVAL_TYPE_MODULE : JS_EVAL_TYPE_GLOBAL));free(source);
    int failed=JS_IsException(value);if(failed)exception(ctx);
    if(!failed){const char*s=JS_ToCString(ctx,value);printf("JS_RESULT:%s\n",s?s:"unknown");JS_FreeCString(ctx,s);}
    JS_FreeValue(ctx,value);
    JSContext *job_ctx=ctx;unsigned jobs=0;int result=0;
    while(!failed&&(result=JS_ExecutePendingJob(rt,&job_ctx))>0&&++jobs<128){}
    if(result<0){exception(job_ctx);failed=1;}
    if(jobs>=128)failed=1;
    for(unsigned i=0;i<128;i++)if(active[i]){
        JSValue reason=JS_PromiseResult(ctx,rejected[i]);
        const char *message=JS_ToCString(ctx,reason);
        fprintf(stderr,"JS_REJECTION:%s\n",message?message:"unknown");
        JS_FreeCString(ctx,message);JS_FreeValue(ctx,reason);JS_FreeValue(ctx,rejected[i]);active[i]=0;failed=1;
    }
    if(rejected_overflow)failed=1;
    JSMemoryUsage usage;JS_ComputeMemoryUsage(rt,&usage);
    printf("JS_MEMORY_SAMPLE:malloc=%lld used=%lld objects=%lld\n", (long long)usage.malloc_size,(long long)usage.memory_used_size,(long long)usage.obj_count);
    JS_FreeContext(ctx);JS_FreeRuntime(rt);return failed?1:0;
}
