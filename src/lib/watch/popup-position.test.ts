import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { placePopup, POPUP_EDGE_PX, rectsOverlap, type Rect } from './popup-position';

const viewport = { width: 1440, height: 900 };
const popup = { width: 360, height: 240 };

function rect(left: number, top: number, width: number, height: number): Rect {
  return { left, top, right: left + width, bottom: top + height };
}

describe('rectsOverlap', () => {
  test('shared area overlaps; touching edges and gaps do not', () => {
    assert.equal(rectsOverlap(rect(0, 0, 10, 10), rect(5, 5, 10, 10)), true);
    assert.equal(rectsOverlap(rect(0, 0, 10, 10), rect(10, 0, 10, 10)), false);
    assert.equal(rectsOverlap(rect(0, 0, 10, 10), rect(0, 10, 10, 10)), false);
    assert.equal(rectsOverlap(rect(0, 0, 10, 10), rect(20, 20, 5, 5)), false);
  });
});

describe('placePopup (UI spec § 4.3)', () => {
  test('right of the card, top aligned, touching it, when width plus 16px fits', () => {
    const card = rect(300, 500, 525, 300);
    assert.deepEqual(placePopup(card, popup, viewport, null), { side: 'right', left: 825, top: 500 });
  });

  test('left of the card when the right side is too narrow', () => {
    const card = rect(840, 500, 525, 300);
    assert.deepEqual(placePopup(card, popup, viewport, null), { side: 'left', left: 480, top: 500 });
  });

  test('right needs the 16px margin too: exactly fitting without it goes left', () => {
    const card = rect(500, 400, 580, 300); // right edge 1080; 1080 + 360 = 1440 leaves no margin
    assert.equal(placePopup(card, popup, viewport, null).side, 'left');
  });

  test('directly below the card when neither side fits', () => {
    const narrow = { width: 800, height: 900 };
    const card = rect(40, 200, 720, 400);
    assert.deepEqual(placePopup(card, popup, narrow, null), { side: 'below', left: 40, top: 600 });
  });

  test('clamps horizontally to 16px from both viewport edges', () => {
    const narrow = { width: 800, height: 1400 };
    assert.equal(placePopup(rect(0, 100, 790, 300), popup, narrow, null).left, POPUP_EDGE_PX);
    // Too wide for either side and starting near the right edge: pulled back to 16px from it.
    const placed = placePopup(rect(500, 100, 290, 300), { width: 600, height: 240 }, narrow, null);
    assert.equal(placed.side, 'below');
    assert.equal(placed.left, 800 - POPUP_EDGE_PX - 600);
  });

  test('clamps the top to at least 16px', () => {
    const card = rect(300, -50, 525, 300);
    assert.equal(placePopup(card, popup, viewport, null).top, POPUP_EDGE_PX);
  });

  test('a first-row card: top is clamped to the player bottom, never above it', () => {
    const player = rect(300, 80, 1080, 420); // bottom 500
    const card = rect(300, 420, 525, 300); // top inside the player's vertical range
    const placed = placePopup(card, popup, viewport, player);
    assert.deepEqual(placed, { side: 'right', left: 825, top: 500 });
  });

  test('clamps the bottom to the viewport minus 16px', () => {
    const card = rect(300, 800, 525, 300);
    assert.equal(placePopup(card, popup, viewport, null).top, 900 - 16 - 240);
  });

  test('the bottom clamp gives way to the player clamp', () => {
    const player = rect(300, 100, 1080, 600); // bottom 700
    const card = rect(300, 800, 525, 300);
    const placed = placePopup(card, popup, viewport, player);
    assert.equal(placed.top, 700);
    assert.ok(placed.top + popup.height > viewport.height - 16, 'runs off the bottom rather than onto the player');
  });

  test('a player scrolled above the viewport does not push the popup down', () => {
    const player = rect(300, -700, 1080, 500); // bottom -200
    const card = rect(300, 100, 525, 300);
    assert.equal(placePopup(card, popup, viewport, player).top, 100);
  });

  test('sweep: no card position, viewport or player rect gives a popup over the player', () => {
    const viewports = [{ width: 1440, height: 900 }, { width: 1120, height: 700 }, { width: 800, height: 600 }];
    const players = [
      null,
      rect(300, 80, 1080, 420),
      rect(300, -700, 1080, 500),
      rect(300, -200, 1080, 420),
      rect(16, 0, 768, 432),
      rect(300, 600, 1080, 420),
    ];
    let checked = 0;
    for (const vp of viewports) {
      for (const player of players) {
        for (let left = 0; left <= vp.width - 200; left += 120) {
          for (let top = -300; top <= vp.height; top += 75) {
            for (const size of [{ width: 360, height: 240 }, { width: 560, height: 420 }]) {
              const card = rect(left, top, 200 + (left % 3) * 150, 260);
              const placed = placePopup(card, size, vp, player);
              checked++;
              assert.ok(['right', 'left', 'below'].includes(placed.side));
              assert.ok(placed.left >= POPUP_EDGE_PX || size.width > vp.width - 2 * POPUP_EDGE_PX);
              assert.ok(placed.top >= POPUP_EDGE_PX);
              if (player) {
                const box = { left: placed.left, top: placed.top, right: placed.left + size.width, bottom: placed.top + size.height };
                assert.equal(rectsOverlap(box, player), false, JSON.stringify({ vp, player, card, size, placed }));
              }
            }
          }
        }
      }
    }
    assert.ok(checked > 1000);
  });
});
