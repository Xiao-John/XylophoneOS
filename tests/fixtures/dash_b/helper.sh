# SPDX-License-Identifier: Apache-2.0
classify_source() {
    case "$1" in
        *.c) printf 'case=c\n' ;;
        *.cpp) printf 'case=cpp\n' ;;
        *) printf 'case=other\n'; return 1 ;;
    esac
}

compile_c_app() {
    "$CC" -static --sysroot=/sysroot -I/src "$@"
}
