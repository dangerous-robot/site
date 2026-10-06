import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** The working version: the first line of VERSION.md, read at build time. */
export const SITE_VERSION = readFileSync(resolve('VERSION.md'), 'utf-8').split('\n')[0].trim();
