// SPDX-License-Identifier: Apache-2.0
JSON.stringify(Object.fromEntries(['document','Worker','MessageChannel','WebAssembly','fetch','URL','TextEncoder','crypto','indexedDB','localStorage','navigator'].map(name=>[name,typeof globalThis[name]])))
