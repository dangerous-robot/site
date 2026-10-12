// Hover previews switch and frame cycling (UI spec § 4.4, § 4.5). Emits
// watch:preview when the effective setting changes; stops any cycle on
// watch:playlist and watch:video.
import {
  ATTR,
  CLASS,
  MQ_FINE_POINTER,
  MQ_REDUCED_MOTION,
  PREVIEWS_STORAGE_KEY,
  TESTID,
  emitWatch,
  onWatch,
} from '../../../lib/watch/contract';
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
import { frameFadeMs } from '../../../lib/watch/timings';
import type { FrameTier, WatchPlaylistView } from '../../../lib/watch/types';

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

interface Active {
  card: HTMLElement;
  cycle: FrameCycle;
  /** True once frames were requested; before that, pointer movement restarts the rest delay. */
  requested: boolean;
}

export function initPreview(root: HTMLElement, bus: EventTarget, _data: WatchPlaylistView[]): void {
  const html = document.documentElement;
  const finePointer = matchMedia(MQ_FINE_POINTER);
  const osReduce = matchMedia(MQ_REDUCED_MOTION);
  const switchEl = root.querySelector<HTMLElement>(`[data-testid="${TESTID.previewSwitch}"]`);
  const hint = root.querySelector<HTMLElement>(`[data-testid="${TESTID.previewHint}"]`);
  const radios = switchEl ? [...switchEl.querySelectorAll<HTMLButtonElement>('[role="radio"]')] : [];
  const thumbSelector = `[data-testid="${TESTID.thumb}"]`;
  // One cache for the page, so a second hover on a card makes no new requests.
  const load = createFrameCache(imageFrameLoader(() => new Image()));

  const reduceOn = () => osReduce.matches || html.dataset.motion === 'reduce';
  let stored = readStored();
  let enabled = previewsEnabled(stored, osReduce.matches, html.dataset.motion === 'reduce');
  let active: Active | null = null;

  function render(): void {
    const siteReduce = html.dataset.motion === 'reduce';
    const checked = enabled ? 'on' : 'off';
    for (const radio of radios) {
      const on = radio.getAttribute(ATTR.value) === checked;
      radio.setAttribute('aria-checked', String(on));
      // Roving tabindex: the group is one tab stop, arrows move within it.
      radio.tabIndex = on ? 0 : -1;
    }
    if (hint) hint.hidden = !previewsHintShown(stored, osReduce.matches, siteReduce);
    if (switchEl) switchEl.hidden = !finePointer.matches;
  }

  function update(): void {
    const previous = enabled;
    enabled = previewsEnabled(stored, osReduce.matches, html.dataset.motion === 'reduce');
    render();
    if (enabled === previous) return;
    if (!enabled) stop();
    emitWatch(bus, 'watch:preview', { enabled });
  }

  function layersFor(card: HTMLElement): [HTMLImageElement, HTMLImageElement] | null {
    const media = card.querySelector<HTMLElement>(`.${CLASS.thumbMedia}`);
    if (!media) return null;
    const existing = media.querySelectorAll<HTMLImageElement>(`.${CLASS.thumbFrame}`);
    if (existing.length === 2) return [existing[0], existing[1]];
    // Right after the cover, so the duration badge still paints on top.
    const anchor = media.querySelector('img');
    const made = [0, 1].map(() => {
      const img = document.createElement('img');
      img.className = CLASS.thumbFrame;
      img.alt = '';
      img.setAttribute('aria-hidden', 'true');
      img.referrerPolicy = 'no-referrer';
      img.decoding = 'async';
      return img;
    }) as [HTMLImageElement, HTMLImageElement];
    if (anchor) anchor.after(...made);
    else media.prepend(...made);
    return made;
  }

  // The layer CSS fades every opacity change; restore must be instant and a
  // reduce setting drops the crossfade, so duration is set per change.
  function setShown(layer: HTMLImageElement, shown: boolean, fadeMs: number): void {
    layer.style.transitionDuration = `${fadeMs}ms`;
    layer.classList.toggle(CLASS.frameShown, shown);
  }

  function restore(card: HTMLElement): void {
    card.removeAttribute(ATTR.previewing);
    card.removeAttribute(ATTR.frame);
    const media = card.querySelector(`.${CLASS.thumbMedia}`);
    media?.querySelectorAll<HTMLImageElement>(`.${CLASS.thumbFrame}`).forEach((layer) => setShown(layer, false, 0));
  }

  function stop(): void {
    if (!active) return;
    const { card, cycle } = active;
    active = null;
    cycle.stop();
    restore(card);
  }

  function start(card: HTMLElement): void {
    stop();
    const id = card.getAttribute(ATTR.videoId);
    const tier = card.getAttribute(ATTR.frameTier);
    if (!enabled || !finePointer.matches || !id || (tier !== 'sd' && tier !== 'mq')) return;

    let front: HTMLImageElement | null = null;
    let hideBack: unknown = null;
    const self: Active = {
      card,
      requested: false,
      cycle: startFrameCycle({
        urls: frameUrls(id, tier as FrameTier),
        clock: systemClock,
        load: (url, done) => {
          self.requested = true;
          return load(url, done);
        },
        onFrame: (frame, url) => {
          const layers = layersFor(card);
          if (!layers) return;
          const [lower, upper] = layers;
          const fade = frameFadeMs(reduceOn());
          const back = front;
          const next = back === lower ? upper : lower;
          next.src = url;
          // Layers keep their DOM order (moving a node would skip its
          // transition), so the crossfade runs on whichever layer is on top.
          if (!back || next === upper) {
            setShown(next, true, fade);
            if (back) hideBack = systemClock.setTimeout(() => setShown(back, false, 0), fade);
          } else {
            setShown(next, true, 0);
            setShown(back, false, fade);
          }
          front = next;
          card.setAttribute(ATTR.previewing, 'true');
          card.setAttribute(ATTR.frame, String(frame));
        },
        onRestore: () => {
          if (hideBack !== null) systemClock.clearTimeout(hideBack);
        },
        onNoPreview: () => {
          if (active === self) active = null;
        },
      }),
    };
    active = self;
  }

  function cardFrom(target: EventTarget | null): HTMLElement | null {
    return target instanceof Element ? target.closest<HTMLElement>(thumbSelector) : null;
  }

  // Enter and leave do not bubble, but a capturing listener on root sees them.
  root.addEventListener(
    'pointerenter',
    (event) => {
      if (event.pointerType !== 'mouse' || !(event.target instanceof Element) || !event.target.matches(thumbSelector)) return;
      start(event.target as HTMLElement);
    },
    true,
  );
  root.addEventListener(
    'pointerleave',
    (event) => {
      if (active && event.target === active.card) stop();
    },
    true,
  );
  // Delays count from when the pointer comes to rest (UI spec § 4.1).
  root.addEventListener('pointermove', (event) => {
    if (!active || active.requested || event.pointerType !== 'mouse') return;
    const card = cardFrom(event.target);
    if (card === active.card) start(card);
  });
  root.addEventListener('focusin', (event) => {
    const card = cardFrom(event.target);
    if (card && card === event.target && card.matches(':focus-visible')) start(card);
  });
  root.addEventListener('focusout', (event) => {
    if (active && event.target === active.card) stop();
  });
  root.addEventListener('click', stop, true);
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') stop();
  });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') stop();
  });
  onWatch(bus, 'watch:playlist', stop);
  onWatch(bus, 'watch:video', stop);

  function choose(radio: HTMLButtonElement): void {
    const value = parseStoredPreviews(radio.getAttribute(ATTR.value));
    if (!value) return;
    stored = value;
    writeStored(value);
    update();
  }

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
  finePointer.addEventListener('change', () => {
    if (!finePointer.matches) stop();
    render();
  });

  render();
}
