// Popup placement for /watch cards (UI spec § 4.3). The popup is
// position: fixed, so every rect here is in viewport coordinates, as
// getBoundingClientRect returns them. YouTube's Required Minimum
// Functionality rule forbids covering the player, so there is no "above".

/** A DOMRect satisfies this. */
export interface Rect {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface Size {
  width: number;
  height: number;
}

export type PopupSide = 'right' | 'left' | 'below';

export interface PopupPlacement {
  top: number;
  left: number;
  side: PopupSide;
}

export const POPUP_EDGE_PX = 16;

/** True when the two rects share any area; touching edges do not count. */
export function rectsOverlap(a: Rect, b: Rect): boolean {
  return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
}

export function placePopup(card: Rect, popupSize: Size, viewport: Size, playerRect: Rect | null): PopupPlacement {
  const { width, height } = popupSize;
  let side: PopupSide;
  let left: number;
  let top: number;

  if (card.right + width + POPUP_EDGE_PX <= viewport.width) {
    side = 'right';
    left = card.right;
    top = card.top;
  } else if (card.left - width - POPUP_EDGE_PX >= 0) {
    side = 'left';
    left = card.left - width;
    top = card.top;
  } else {
    side = 'below';
    left = card.left;
    top = card.bottom;
  }

  left = Math.max(POPUP_EDGE_PX, Math.min(left, viewport.width - POPUP_EDGE_PX - width));

  // The bottom clamp comes first so the player clamp overrides it: a popup
  // may run off the bottom of the viewport but never onto the player. This
  // clamp alone enforces the never-cover rule; the sweep test guards it.
  const minTop = Math.max(POPUP_EDGE_PX, playerRect?.bottom ?? POPUP_EDGE_PX);
  top = Math.max(minTop, Math.min(top, viewport.height - POPUP_EDGE_PX - height));
  return { top, left, side };
}
