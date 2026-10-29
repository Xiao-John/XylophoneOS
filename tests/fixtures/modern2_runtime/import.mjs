// SPDX-License-Identifier: Apache-2.0
import { answer } from './module.mjs';
if (answer !== 42) throw Error('module mismatch');
