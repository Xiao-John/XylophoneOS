// SPDX-License-Identifier: Apache-2.0
const answer = await Promise.resolve(42);
if (answer !== 42) throw Error('top-level await mismatch');
export { answer };
