/* Generated automatically from /Users/perry_guo/Documents/ChatGPT/os/XylophoneOS-modern2-python/.cache/xos_seed/cpython/d2d064e8db8332bc7d91/source/Modules/config.c.in by makesetup. */
/* Module configuration */

/* !!! !!! !!! This file is edited by the makesetup script !!! !!! !!! */

/* This file contains the table of built-in modules.
   See create_builtin() in import.c. */

#include "Python.h"

#ifdef __cplusplus
extern "C" {
#endif


extern PyObject* PyInit__imaging(void);
extern PyObject* PyInit__sqlite3(void);
extern PyObject* PyInit_array(void);
extern PyObject* PyInit__asyncio(void);
extern PyObject* PyInit__bisect(void);
extern PyObject* PyInit__csv(void);
extern PyObject* PyInit__heapq(void);
extern PyObject* PyInit__json(void);
extern PyObject* PyInit__lsprof(void);
extern PyObject* PyInit__pickle(void);
extern PyObject* PyInit__queue(void);
extern PyObject* PyInit__random(void);
extern PyObject* PyInit__struct(void);
extern PyObject* PyInit__interpreters(void);
extern PyObject* PyInit__interpchannels(void);
extern PyObject* PyInit__interpqueues(void);
extern PyObject* PyInit__zoneinfo(void);
extern PyObject* PyInit_math(void);
extern PyObject* PyInit_cmath(void);
extern PyObject* PyInit__statistics(void);
extern PyObject* PyInit__decimal(void);
extern PyObject* PyInit_binascii(void);
extern PyObject* PyInit_zlib(void);
extern PyObject* PyInit__md5(void);
extern PyObject* PyInit__sha1(void);
extern PyObject* PyInit__sha2(void);
extern PyObject* PyInit__sha3(void);
extern PyObject* PyInit__blake2(void);
extern PyObject* PyInit__hmac(void);
extern PyObject* PyInit_pyexpat(void);
extern PyObject* PyInit__elementtree(void);
extern PyObject* PyInit__codecs_cn(void);
extern PyObject* PyInit__codecs_hk(void);
extern PyObject* PyInit__codecs_iso2022(void);
extern PyObject* PyInit__codecs_jp(void);
extern PyObject* PyInit__codecs_kr(void);
extern PyObject* PyInit__codecs_tw(void);
extern PyObject* PyInit__multibytecodec(void);
extern PyObject* PyInit_unicodedata(void);
extern PyObject* PyInit_atexit(void);
extern PyObject* PyInit_faulthandler(void);
extern PyObject* PyInit_posix(void);
extern PyObject* PyInit__signal(void);
extern PyObject* PyInit__tracemalloc(void);
extern PyObject* PyInit__suggestions(void);
extern PyObject* PyInit__datetime(void);
extern PyObject* PyInit__codecs(void);
extern PyObject* PyInit__collections(void);
extern PyObject* PyInit_errno(void);
extern PyObject* PyInit__io(void);
extern PyObject* PyInit_itertools(void);
extern PyObject* PyInit__sre(void);
extern PyObject* PyInit__sysconfig(void);
extern PyObject* PyInit__thread(void);
extern PyObject* PyInit_time(void);
extern PyObject* PyInit__types(void);
extern PyObject* PyInit__typing(void);
extern PyObject* PyInit__weakref(void);
extern PyObject* PyInit__abc(void);
extern PyObject* PyInit__functools(void);
extern PyObject* PyInit__locale(void);
extern PyObject* PyInit__opcode(void);
extern PyObject* PyInit__operator(void);
extern PyObject* PyInit__stat(void);
extern PyObject* PyInit__symtable(void);

/* -- ADDMODULE MARKER 1 -- */

extern PyObject* PyMarshal_Init(void);
extern PyObject* PyInit__imp(void);
extern PyObject* PyInit_gc(void);
extern PyObject* PyInit__ast(void);
extern PyObject* PyInit__tokenize(void);
extern PyObject* PyInit__contextvars(void);
extern PyObject* _PyWarnings_Init(void);
extern PyObject* PyInit__string(void);

struct _inittab _PyImport_Inittab[] = {

    {"_imaging", PyInit__imaging},
    {"_sqlite3", PyInit__sqlite3},
    {"array", PyInit_array},
    {"_asyncio", PyInit__asyncio},
    {"_bisect", PyInit__bisect},
    {"_csv", PyInit__csv},
    {"_heapq", PyInit__heapq},
    {"_json", PyInit__json},
    {"_lsprof", PyInit__lsprof},
    {"_pickle", PyInit__pickle},
    {"_queue", PyInit__queue},
    {"_random", PyInit__random},
    {"_struct", PyInit__struct},
    {"_interpreters", PyInit__interpreters},
    {"_interpchannels", PyInit__interpchannels},
    {"_interpqueues", PyInit__interpqueues},
    {"_zoneinfo", PyInit__zoneinfo},
    {"math", PyInit_math},
    {"cmath", PyInit_cmath},
    {"_statistics", PyInit__statistics},
    {"_decimal", PyInit__decimal},
    {"binascii", PyInit_binascii},
    {"zlib", PyInit_zlib},
    {"_md5", PyInit__md5},
    {"_sha1", PyInit__sha1},
    {"_sha2", PyInit__sha2},
    {"_sha3", PyInit__sha3},
    {"_blake2", PyInit__blake2},
    {"_hmac", PyInit__hmac},
    {"pyexpat", PyInit_pyexpat},
    {"_elementtree", PyInit__elementtree},
    {"_codecs_cn", PyInit__codecs_cn},
    {"_codecs_hk", PyInit__codecs_hk},
    {"_codecs_iso2022", PyInit__codecs_iso2022},
    {"_codecs_jp", PyInit__codecs_jp},
    {"_codecs_kr", PyInit__codecs_kr},
    {"_codecs_tw", PyInit__codecs_tw},
    {"_multibytecodec", PyInit__multibytecodec},
    {"unicodedata", PyInit_unicodedata},
    {"atexit", PyInit_atexit},
    {"faulthandler", PyInit_faulthandler},
    {"posix", PyInit_posix},
    {"_signal", PyInit__signal},
    {"_tracemalloc", PyInit__tracemalloc},
    {"_suggestions", PyInit__suggestions},
    {"_datetime", PyInit__datetime},
    {"_codecs", PyInit__codecs},
    {"_collections", PyInit__collections},
    {"errno", PyInit_errno},
    {"_io", PyInit__io},
    {"itertools", PyInit_itertools},
    {"_sre", PyInit__sre},
    {"_sysconfig", PyInit__sysconfig},
    {"_thread", PyInit__thread},
    {"time", PyInit_time},
    {"_types", PyInit__types},
    {"_typing", PyInit__typing},
    {"_weakref", PyInit__weakref},
    {"_abc", PyInit__abc},
    {"_functools", PyInit__functools},
    {"_locale", PyInit__locale},
    {"_opcode", PyInit__opcode},
    {"_operator", PyInit__operator},
    {"_stat", PyInit__stat},
    {"_symtable", PyInit__symtable},

/* -- ADDMODULE MARKER 2 -- */
    {"PIL._imaging", PyInit__imaging},

    /* This module lives in marshal.c */
    {"marshal", PyMarshal_Init},

    /* This lives in import.c */
    {"_imp", PyInit__imp},

    /* This lives in Python/Python-ast.c */
    {"_ast", PyInit__ast},

    /* This lives in Python/Python-tokenize.c */
    {"_tokenize", PyInit__tokenize},

    /* These entries are here for sys.builtin_module_names */
    {"builtins", NULL},
    {"sys", NULL},

    /* This lives in gcmodule.c */
    {"gc", PyInit_gc},

    /* This lives in Python/_contextvars.c */
    {"_contextvars", PyInit__contextvars},

    /* This lives in _warnings.c */
    {"_warnings", _PyWarnings_Init},

    /* This lives in Objects/unicodeobject.c */
    {"_string", PyInit__string},

    /* Sentinel */
    {0, 0}
};


#ifdef __cplusplus
}
#endif
