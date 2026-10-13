import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { LIST_WIDTH } from './contract';
import { clampListWidth, nowPlayingLine, switcherPos, triggerLabel } from './layout';

describe('clampListWidth', () => {
  it('keeps widths inside the limits', () => {
    assert.equal(clampListWidth(LIST_WIDTH.initial), LIST_WIDTH.initial);
    assert.equal(clampListWidth(LIST_WIDTH.min - 1), LIST_WIDTH.min);
    assert.equal(clampListWidth(LIST_WIDTH.max + 100), LIST_WIDTH.max);
  });

  it('rounds drag positions to whole pixels', () => {
    assert.equal(clampListWidth(401.6), 402);
  });
});

describe('nowPlayingLine', () => {
  const playlists = [
    { slug: 'alpha', name: 'Alpha list', videos: [{ id: 'a1', title: 'First' }] },
    { slug: 'bravo', name: 'Bravo list', videos: [{ id: 'b1', title: 'Second' }] },
  ];

  it('names the video when its playlist is shown', () => {
    assert.deepEqual(nowPlayingLine('alpha', { slug: 'alpha', id: 'a1' }, playlists), { text: 'Now playing: First', action: 'scroll' });
  });

  it('offers the way back when another playlist is shown', () => {
    assert.deepEqual(nowPlayingLine('bravo', { slug: 'alpha', id: 'a1' }, playlists), {
      text: 'Back to now playing in Alpha list',
      action: 'switch',
    });
  });

  it('is empty when nothing is in the player or the video is unknown', () => {
    assert.deepEqual(nowPlayingLine('alpha', null, playlists), { text: '', action: 'none' });
    assert.deepEqual(nowPlayingLine('alpha', { slug: 'alpha', id: 'zz' }, playlists), { text: '', action: 'none' });
  });
});

describe('switcher labels', () => {
  it('counts from one', () => {
    assert.equal(switcherPos(0, 3), '1 of 3');
  });

  it('names the playlist and the action', () => {
    assert.equal(triggerLabel('Alpha list'), 'Playlist: Alpha list. Change playlist');
  });
});
