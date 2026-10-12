import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { coverSrcset, frameUrls, isPlaceholder } from './frames';

describe('frameUrls', () => {
  test('sd tier gives sd1 to sd3 on i.ytimg.com', () => {
    assert.deepEqual(frameUrls('dQw4w9WgXcQ', 'sd'), [
      'https://i.ytimg.com/vi/dQw4w9WgXcQ/sd1.jpg',
      'https://i.ytimg.com/vi/dQw4w9WgXcQ/sd2.jpg',
      'https://i.ytimg.com/vi/dQw4w9WgXcQ/sd3.jpg',
    ]);
  });

  test('mq tier gives mq1 to mq3, never maxres', () => {
    const urls = frameUrls('abc_DEF-123', 'mq');
    assert.deepEqual(urls, [
      'https://i.ytimg.com/vi/abc_DEF-123/mq1.jpg',
      'https://i.ytimg.com/vi/abc_DEF-123/mq2.jpg',
      'https://i.ytimg.com/vi/abc_DEF-123/mq3.jpg',
    ]);
    assert.ok(urls.every((u) => !u.includes('maxres')));
  });

  test('an id with path characters cannot leave the /vi/<id>/ segment', () => {
    assert.equal(frameUrls('../x?y', 'mq')[0], 'https://i.ytimg.com/vi/..%2Fx%3Fy/mq1.jpg');
  });
});

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

describe('isPlaceholder', () => {
  test('the 120px grey 404 image and anything narrower is a placeholder', () => {
    assert.equal(isPlaceholder(120), true);
    assert.equal(isPlaceholder(0), true);
  });

  test('control: real frame widths are not placeholders', () => {
    assert.equal(isPlaceholder(121), false);
    assert.equal(isPlaceholder(320), false);
    assert.equal(isPlaceholder(640), false);
  });
});
