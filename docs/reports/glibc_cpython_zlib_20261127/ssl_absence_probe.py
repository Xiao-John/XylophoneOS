# SPDX-License-Identifier: Apache-2.0
try:
    import _ssl
except ModuleNotFoundError as error:
    if error.name != '_ssl':
        raise
    print('CPYTHON_SSL_MODULE_MISSING')
else:
    raise AssertionError('unexpected SSL support in the zlib-only candidate')
