// SPDX-License-Identifier: Apache-2.0
JSON.stringify(Object.fromEntries(['document','window','EventTarget','Worker','WebAssembly','fetch','URL','crypto','crossOriginIsolated','SharedArrayBuffer','Atomics'].map(name => [name, typeof globalThis[name]])));
