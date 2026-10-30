// SPDX-License-Identifier: Apache-2.0
Promise.resolve(40).then(x => x + 2).then(x => { if (x !== 42) throw Error('Promise job mismatch'); return 'PROMISE_JOBS_DONE'; });
