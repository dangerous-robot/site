// Hover previews switch and frame cycling (UI spec § 4.4, § 4.5). Emits
// watch:preview when the effective setting changes. When to start and stop
// comes from the shared card intent, the same moments the popup uses.
import { ATTR, CLASS, PREVIEWS_STORAGE_KEY, TESTID, emitWatch } from '../../../lib/watch/contract';
import type { PreviewsStoredValue } from '../../../lib/watch/contract';
import { frameUrls } from '../../../lib/watch/frames';
import {
  createFrameCache,
  imageFrameLoader,
  parseStoredPreviews,
  previewsEnabled,
  previewsHintShown,
  startFrameCycle,
  systemClock,
  type FrameCycle,
} from '../../../lib/watch/preview';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { onCardIntent } from './cardIntent';
import { byTestId, finePointer, osReduceMotion } from './dom';

// Storage can throw in private modes or with site data blocked; previews
// then just follow the reduce-motion settings for this visit.
function readStored(): PreviewsStoredValue | null {
  try {
    return parseStoredPreviews(localStorage.getItem(PREVIEWS_STORAGE_KEY));
  } catch {
    return null;
  }
}

function writeStored(value: PreviewsStoredValue): void {
  try {
    localStorage.setItem(PREVIEWS_STORAGE_KEY, value);
  } catch {
    /* the choice still applies until reload */
  }
}

type Layers = [lower: HTMLImageElement, upper: HTMLImageElement];

export function initPreview(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  const html = document.documentElement;
  const fine = finePointer();
  const osReduce = osReduceMotion();
  const switchEl = byTestId(root, TESTID.previewSwitch);
  const hint = byTestId(root, TESTID.previewHint);
  const radios = switchEl ? [...switchEl.querySelectorAll<HTMLButtonElement>('[role="radio"]')] : [];
  // One cache for the page, so a second hover on a card makes no new requests.
  const load = createFrameCache(imageFrameLoader(() => new Image()));
  const layerCache = new WeakMap<HTMLElement, Layers>();

  /** Both reduce signals; A11yControl sets data-motion, but it may not have run yet. */
  const reduce = () => ({ os: osReduce.matches, site: html.dataset.motion === 'reduce' });
  const isEnabled = () => {
    const { os, site } = reduce();
    return previewsEnabled(stored, os, site);
  };

  let stored = readStored();
  let enabled = isEnabled();
  let active: { card: HTMLElement; cycle: FrameCycle } | null = null;

  const render = () => {
    const checked = enabled ? 'on' : 'off';
    for (const radio of radios) {
      const on = radio.getAttribute(ATTR.value) === checked;
      radio.setAttribute('aria-checked', String(on));
      // Roving tabindex: the group is one tab stop, arrows move within it.
      radio.tabIndex = on ? 0 : -1;
    }
    if (hint) {
      const { os, site } = reduce();
      hint.hidden = !previewsHintShown(stored, os, site);
    }
    if (switchEl) switchEl.hidden = !fine.matches;
  };

  const update = () => {
    const previous = enabled;
    enabled = isEnabled();
    render();
    if (enabled === previous) return;
    if (!enabled) stop();
    emitWatch(bus, 'watch:preview', { enabled });
  };

  const layersFor = (card: HTMLElement): Layers | null => {
    const cached = layerCache.get(card);
    if (cached) return cached;
    const media = card.querySelector<HTMLElement>(`.${CLASS.thumbMedia}`);
    if (!media) return null;
    const made = [0, 1].map(() => {
      const img = document.createElement('img');
      img.className = CLASS.thumbFrame;
      img.alt = '';
      img.setAttribute('aria-hidden', 'true');
      img.referrerPolicy = 'no-referrer';
      img.decoding = 'async';
      return img;
    }) as Layers;
    // Right after the cover, so the duration badge still paints on top.
    const cover = media.querySelector('img');
    if (cover) cover.after(...made);
    else media.prepend(...made);
    layerCache.set(card, made);
    return made;
  };

  // Removing data-previewing drops the layer transition (VideoThumb CSS),
  // so the cover comes back at once.
  const restore = (card: HTMLElement) => {
    card.removeAttribute(ATTR.previewing);
    card.removeAttribute(ATTR.frame);
    for (const layer of layerCache.get(card) ?? []) layer.classList.remove(CLASS.frameShown);
  };

  function stop(): void {
    if (!active) return;
    const { card, cycle } = active;
    active = null;
    cycle.stop();
    restore(card);
  }

  const start = (card: HTMLElement, restedMs: number) => {
    stop();
    const id = card.getAttribute(ATTR.videoId);
    const tier = card.getAttribute(ATTR.frameTier);
    if (!enabled || !id || (tier !== 'sd' && tier !== 'mq')) return;

    let front: HTMLImageElement | null = null;
    // onNoPreview can run inside startFrameCycle when every frame is a
    // cached failure, before the cycle is assigned.
    let ended = false;
    const cycle = startFrameCycle({
      urls: frameUrls(id, tier),
      clock: systemClock,
      load,
      elapsedMs: restedMs,
      onFrame: (frame, url) => {
        const layers = layersFor(card);
        if (!layers) return;
        const [lower, upper] = layers;
        // Only the upper layer fades (VideoThumb CSS): it fades in over the
        // lower, or out to reveal a lower that took the new frame while
        // hidden beneath it. Layers keep their DOM order, since moving a node
        // would skip its transition.
        const next = front === upper ? lower : upper;
        next.src = url;
        next.classList.add(CLASS.frameShown);
        if (next === lower) upper.classList.remove(CLASS.frameShown);
        front = next;
        card.setAttribute(ATTR.previewing, 'true');
        card.setAttribute(ATTR.frame, String(frame));
      },
      onNoPreview: () => {
        ended = true;
        if (active?.card === card) active = null;
      },
    });
    if (!ended) active = { card, cycle };
  };

  onCardIntent(root, bus, {
    rest: (card, _source, restedMs) => start(card, restedMs),
    leave: (card) => {
      if (active?.card === card) stop();
    },
    cancel: stop,
  });

  const choose = (radio: HTMLButtonElement) => {
    const value = parseStoredPreviews(radio.getAttribute(ATTR.value));
    if (!value) return;
    stored = value;
    writeStored(value);
    update();
  };

  for (const radio of radios) radio.addEventListener('click', () => choose(radio));
  switchEl?.addEventListener('keydown', (event) => {
    const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown';
    const back = event.key === 'ArrowLeft' || event.key === 'ArrowUp';
    if (!forward && !back) return;
    const at = radios.indexOf(document.activeElement as HTMLButtonElement);
    if (at === -1) return;
    event.preventDefault();
    const next = radios[(at + (forward ? 1 : radios.length - 1)) % radios.length];
    next.focus();
    choose(next);
  });

  // With nothing stored the state follows both reduce signals live;
  // A11yControl changes data-motion without a reload.
  osReduce.addEventListener('change', update);
  new MutationObserver(update).observe(html, { attributes: true, attributeFilter: ['data-motion'] });
  // Card intent stops a running cycle on this change; the switch follows it.
  fine.addEventListener('change', render);

  render();
}
