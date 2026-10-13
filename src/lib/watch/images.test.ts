import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { coverSrcset } from './images';

describe('coverSrcset', () => {
  test('passes a built srcset through', () => {
    const srcset = 'https://i.ytimg.com/vi/a/mqdefault.jpg 320w, https://i.ytimg.com/vi/a/hqdefault.jpg 480w';
    assert.equal(coverSrcset({ src: 'https://i.ytimg.com/vi/a/mqdefault.jpg', srcset }), srcset);
  });

  test('an empty or blank srcset gives undefined so the attribute is dropped', () => {
    assert.equal(coverSrcset({ src: 'https://i.ytimg.com/vi/a/mqdefault.jpg', srcset: '' }), undefined);
    assert.equal(coverSrcset({ src: 'https://i.ytimg.com/vi/a/mqdefault.jpg', srcset: '  ' }), undefined);
  });
});
