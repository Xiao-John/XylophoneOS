// SPDX-License-Identifier: Apache-2.0
(() => {
  const buffer = new ArrayBuffer(64);
  const bytes = new Uint8Array(buffer);
  const view = new DataView(buffer);
  view.setUint32(0, 0x12345678, true);
  if (bytes[0] !== 0x78 || view.getUint32(0, true) !== 0x12345678) throw Error('buffer mismatch');
  bytes.fill(7, 8, 16);
  const copy = bytes.slice(8, 16);
  bytes[8] = 9;
  if (copy[0] !== 7 || copy.length !== 8) throw Error('slice mismatch');
  return 'BUFFER_LANGUAGE_OK';
})();
