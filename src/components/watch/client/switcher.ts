// Playlist switcher: a disclosure button that opens a menu of the other
// playlists over a scrim, and the now-playing line under it. Picking a
// playlist emits watch:playlist; main.ts shows its panel and restores its
// scroll position. Escape or a scrim click closes the menu and puts focus
// back on the trigger.
import { ATTR, CLASS, TESTID, emitWatch, onWatch } from '../../../lib/watch/contract';
import { nowPlayingLine, switcherPos, triggerLabel } from '../../../lib/watch/layout';
import type { WatchPlaylistView } from '../../../lib/watch/types';
import { allByTestId, byTestId, closestByTestId, testid } from './dom';

export function initSwitcher(root: HTMLElement, bus: EventTarget, data: WatchPlaylistView[]): void {
  const switcher = byTestId(root, TESTID.switcher);
  const trigger = switcher && byTestId<HTMLButtonElement>(switcher, TESTID.trigger);
  const menu = switcher && byTestId(switcher, TESTID.menu);
  const np = switcher && byTestId<HTMLButtonElement>(switcher, TESTID.nowPlaying);
  if (!switcher || !trigger || !menu || !np) return;
  const scrim = byTestId(root, TESTID.scrim);
  const pos = byTestId(switcher, TESTID.switcherPos);
  const npText = np.querySelector<HTMLElement>('.watch-np__text');
  const cards = [...trigger.querySelectorAll<HTMLElement>(`[${ATTR.playlist}]`)];
  const items = [...menu.querySelectorAll<HTMLLIElement>(`li[${ATTR.playlist}]`)];
  const options = allByTestId<HTMLButtonElement>(menu, TESTID.option);

  let selected = '';
  let video: { slug: string; id: string } | null = null;

  const isOpen = () => !menu.hidden;
  const visibleOptions = () => options.filter((o) => !o.closest('li')?.hidden);

  const open = () => {
    menu.hidden = false;
    if (scrim) scrim.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    visibleOptions()[0]?.focus();
  };

  const close = (refocus: boolean) => {
    if (!isOpen()) return;
    menu.hidden = true;
    if (scrim) scrim.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (refocus) trigger.focus();
  };

  const renderLine = () => {
    const line = nowPlayingLine(selected, video, data);
    if (npText) npText.textContent = line.text;
    np.disabled = line.action === 'none';
    for (const option of options) {
      const glyph = option.querySelector<HTMLElement>(`.${CLASS.optionPlaying}`);
      if (glyph) glyph.hidden = option.getAttribute(ATTR.playlist) !== video?.slug;
    }
  };

  const scrollToCurrent = () => {
    const row = root.querySelector<HTMLElement>(`${testid(TESTID.panel)}:not([hidden]) ${testid(TESTID.thumb)}[aria-current="true"]`);
    if (!row) return;
    row.focus({ preventScroll: true });
    row.scrollIntoView({ block: 'start' });
  };

  trigger.addEventListener('click', () => (isOpen() ? close(false) : open()));

  menu.addEventListener('click', (event) => {
    const option = closestByTestId(event.target, TESTID.option);
    const slug = option?.getAttribute(ATTR.playlist);
    if (!slug) return;
    // The option is about to hide, so focus goes to the trigger that now shows it.
    close(true);
    if (slug !== selected) emitWatch(bus, 'watch:playlist', { slug });
  });

  switcher.addEventListener('keydown', (event) => {
    if (!isOpen()) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const list = visibleOptions();
    const at = list.indexOf(document.activeElement as HTMLButtonElement);
    if (at < 0) return;
    event.preventDefault();
    const step = event.key === 'ArrowDown' ? 1 : -1;
    list[(at + step + list.length) % list.length].focus();
  });

  // Any press outside the trigger and menu closes it. It runs on mousedown,
  // in the capture phase, so it settles the menu before focus moves: a press
  // on the scrim is cancelled (it would focus <main>, which has tabindex -1,
  // and its release would land on the row underneath) and focus returns to
  // the trigger.
  const anchor = trigger.parentElement ?? switcher;
  document.addEventListener(
    'mousedown',
    (event) => {
      const target = event.target;
      if (!isOpen() || !(target instanceof Node) || anchor.contains(target)) return;
      const onScrim = !!scrim?.contains(target);
      if (onScrim) event.preventDefault();
      close(onScrim);
    },
    true,
  );
  // Tabbing out closes it too, so the scrim never covers a focused row.
  anchor.addEventListener('focusout', (event) => {
    const to = event.relatedTarget;
    if (to instanceof Node && !anchor.contains(to)) close(false);
  });

  np.addEventListener('click', () => {
    const line = nowPlayingLine(selected, video, data);
    if (line.action === 'switch' && video) emitWatch(bus, 'watch:playlist', { slug: video.slug });
    if (line.action !== 'none') scrollToCurrent();
  });

  onWatch(bus, 'watch:playlist', ({ slug }) => {
    const index = data.findIndex((p) => p.slug === slug);
    if (index < 0) return;
    selected = slug;
    for (const card of cards) card.hidden = card.getAttribute(ATTR.playlist) !== slug;
    for (const item of items) item.hidden = item.getAttribute(ATTR.playlist) === slug;
    if (pos) pos.textContent = switcherPos(index, data.length);
    trigger.setAttribute('aria-label', triggerLabel(data[index].name));
    renderLine();
  });

  onWatch(bus, 'watch:video', ({ slug, id }) => {
    video = { slug, id };
    renderLine();
  });

  renderLine();
}
