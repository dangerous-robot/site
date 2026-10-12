import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { indexPlaylists } from './index';

const playlists = [
  { slug: 'alpha', videos: [{ id: 'a1' }, { id: 'shared' }] },
  { slug: 'bravo', videos: [{ id: 'shared' }] },
  { slug: 'empty', videos: [] },
];

describe('indexPlaylists', () => {
  test('finds a playlist by slug', () => {
    assert.equal(indexPlaylists(playlists).bySlug('bravo'), playlists[1]);
    assert.equal(indexPlaylists(playlists).bySlug('nope'), undefined);
  });

  test('finds a video only in the playlist named', () => {
    const index = indexPlaylists(playlists);
    assert.deepEqual(index.findVideo('alpha', 'a1'), { playlist: playlists[0], video: playlists[0].videos[0] });
    assert.equal(index.findVideo('bravo', 'shared')?.playlist, playlists[1]);
    assert.equal(index.findVideo('bravo', 'a1'), null);
    assert.equal(index.findVideo('nope', 'a1'), null);
    assert.equal(index.findVideo('empty', 'a1'), null);
  });

  test('the same payload array gives the same index', () => {
    assert.equal(indexPlaylists(playlists), indexPlaylists(playlists));
    assert.notEqual(indexPlaylists(playlists), indexPlaylists([...playlists]));
  });
});
