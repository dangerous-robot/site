import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { httpUrl } from './httpUrl';

describe('httpUrl', () => {
  test('rejects schemes that run code or embed content', () => {
    for (const url of ['javascript:alert(1)', 'JavaScript:alert(1)', 'data:text/html,<script>', 'vbscript:x', 'ftp://example.org/x']) {
      assert.equal(httpUrl.safeParse(url).success, false, url);
    }
  });

  test('rejects values that are not URLs at all', () => {
    assert.equal(httpUrl.safeParse('example.org').success, false);
    assert.equal(httpUrl.safeParse('').success, false);
  });

  test('control: http and https URLs pass', () => {
    for (const url of ['https://example.org', 'http://example.org/a?b=1#c', 'HTTPS://EXAMPLE.ORG/x']) {
      assert.equal(httpUrl.safeParse(url).success, true, url);
    }
  });
});
