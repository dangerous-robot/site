// Pure rules for the /watch list column: its width limits and the one-line
// "now playing" status under the playlist switcher.
import { LIST_WIDTH } from './contract';

/** "N of M" beside the Playlist label; index is zero-based. */
export function switcherPos(index: number, count: number): string {
  return `${index + 1} of ${count}`;
}

/** The trigger's accessible name: its card says which playlist, the label says what it does. */
export function triggerLabel(playlistName: string): string {
  return `Playlist: ${playlistName}. Change playlist`;
}

export function clampListWidth(px: number): number {
  return Math.max(LIST_WIDTH.min, Math.min(LIST_WIDTH.max, Math.round(px)));
}

interface NamedPlaylist {
  slug: string;
  name: string;
  videos: readonly { id: string; title: string }[];
}

export interface NowPlayingLine {
  text: string;
  /** Same playlist: scroll to the row. Other: switch back first. None: nothing in the player. */
  action: 'scroll' | 'switch' | 'none';
}

/** The status line never disappears (it would shift the list), so with no video it is empty text. */
export function nowPlayingLine(
  selectedSlug: string,
  video: { slug: string; id: string } | null,
  playlists: readonly NamedPlaylist[],
): NowPlayingLine {
  const owner = video ? playlists.find((p) => p.slug === video.slug) : undefined;
  const entry = owner?.videos.find((v) => v.id === video?.id);
  if (!owner || !entry) return { text: '', action: 'none' };
  if (owner.slug === selectedSlug) return { text: `Now playing: ${entry.title}`, action: 'scroll' };
  return { text: `Back to now playing in ${owner.name}`, action: 'switch' };
}
