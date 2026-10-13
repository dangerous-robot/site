// Build-time orchestration for /watch: curated list in, normalized playlists
// out. It never throws: the deploy must stay green whatever the
// API does, so a global failure becomes mode 'none' with one warning.
//
// Log lines carry playlist IDs, counts and API error text only, never API
// titles, so CI logs hold no YouTube API data.
import type { WatchBuildResult, WatchPlaylist } from './types';
import { watchPlaylistSchema, type CuratedPlaylist } from './schema';
import { failedPlaylist, normalizePlaylist, type NormalizedPlaylist } from './normalize';
import { redact, YouTubeError, type ApiPlaylist, type ApiPlaylistItem, type ApiVideo, type YouTubeClient } from './youtube';
import { missingKeyWarning, type WatchEnvironment } from './env';

export interface WatchLog {
  /** One line of the fixed info format; the sink adds the prefix. */
  info(text: string): void;
  warn(text: string): void;
}

/** GitHub workflow-command encoding, so API text cannot end the annotation or start another command. */
export function escapeWorkflowCommand(text: string): string {
  return text.replace(/%/g, '%25').replace(/\r/g, '%0D').replace(/\n/g, '%0A');
}

/**
 * Console sink for the loader. Warnings go to stderr; under GitHub Actions
 * each is repeated on stdout as an annotation, which only works at the start
 * of a line, so it does not go through Astro's prefixed logger.
 */
export function createConsoleLog(
  env: Pick<WatchEnvironment, 'githubActions'>,
  sink: Pick<Console, 'log' | 'warn'> = console,
): WatchLog {
  return {
    info: (text) => sink.log(`[watch loader] ${text}`),
    warn: (text) => {
      sink.warn(`[watch loader] warning: ${text}`);
      if (env.githubActions) sink.log(`::warning title=Watch page::${escapeWorkflowCommand(text)}`);
    },
  };
}

/** null when valid, else the first issue. */
export type EntryCheck = string | null;

/** Schema check for one stored entry; the issue names a path and a schema message, never API text. */
export function validateEntry(entry: WatchPlaylist): EntryCheck {
  const result = watchPlaylistSchema.safeParse(entry);
  if (result.success) return null;
  const first = result.error.issues[0];
  const path = first?.path.length ? `${first.path.join('.')}: ` : '';
  return `${path}${first?.message ?? 'invalid entry'}`;
}

export interface LoadWatchDataOptions {
  /** Parsed by curatedFileSchema, so max_videos has its default. */
  curated: CuratedPlaylist[];
  /** null in none mode (createWatchClient). */
  client: YouTubeClient | null;
  env: Pick<WatchEnvironment, 'mode' | 'key' | 'expectKey'>;
  log: WatchLog;
}

const sentence = (text: string) => (/[.!?]$/.test(text) ? text : `${text}.`);

type Fetched =
  | { curated: CuratedPlaylist; api: ApiPlaylist; result: NormalizedPlaylist }
  | { curated: CuratedPlaylist; api: ApiPlaylist; error: YouTubeError };

/** A playlist-scope error marks one playlist failed; anything else stops the whole load. */
function playlistError(err: unknown): YouTubeError {
  if (err instanceof YouTubeError && err.scope === 'playlist') return err;
  throw err;
}

/**
 * Fetches every readable playlist's videos with as few calls as possible:
 * the first playlistItems page of every playlist in parallel, one batched
 * videos.list for all of them, then further pages only for a playlist still
 * short of max_videos after filtering.
 */
async function fetchPlaylists(
  client: YouTubeClient,
  readable: { curated: CuratedPlaylist; api: ApiPlaylist }[],
  dataMode: WatchPlaylist['dataMode'],
): Promise<Fetched[]> {
  const videos = new Map<string, ApiVideo>();
  const requested = new Set<string>();
  const fetchVideos = async (items: ApiPlaylistItem[]) => {
    const ids = [...new Set(items.map((i) => i.snippet?.resourceId?.videoId).filter((id): id is string => !!id && !requested.has(id)))];
    for (const id of ids) requested.add(id);
    if (ids.length === 0) return;
    for (const v of await client.listVideos(ids)) if (v.id) videos.set(v.id, v);
  };

  const firstPages = await Promise.all(readable.map(async (r) => {
    try {
      return { ...r, page: await client.listPlaylistItemsPage(r.curated.playlist_id) };
    } catch (err) {
      return { ...r, error: playlistError(err) };
    }
  }));
  await fetchVideos(firstPages.flatMap((f) => ('page' in f ? f.page.items : [])));

  // Sequential, so a video one playlist has asked for is always in the map
  // before another playlist that shares it is normalized.
  const out: Fetched[] = [];
  for (const f of firstPages) {
    if (!('page' in f)) {
      out.push(f);
      continue;
    }
    const { curated, api } = f;
    const items = [...f.page.items];
    let next = f.page.nextPageToken;
    const normalize = () => normalizePlaylist({ curated, api, items, videos: [...videos.values()], dataMode });
    let result = normalize();
    try {
      while (next && result.playlist.videos.length < curated.max_videos) {
        const page = await client.listPlaylistItemsPage(curated.playlist_id, next);
        items.push(...page.items);
        next = page.nextPageToken;
        await fetchVideos(page.items);
        result = normalize();
      }
      out.push({ curated, api, result });
    } catch (err) {
      out.push({ curated, api, error: playlistError(err) });
    }
  }
  return out;
}

export async function loadWatchData({ curated, client, env, log }: LoadWatchDataOptions): Promise<WatchBuildResult> {
  const key = env.key ?? '';
  const warnings: string[] = [];
  // Redaction here backs up the client's own, in case an unexpected error
  // carries the key.
  const warn = (text: string) => {
    const safe = redact(text, key);
    warnings.push(safe);
    log.warn(safe);
  };
  const finish = (mode: WatchBuildResult['mode'], playlists: WatchPlaylist[], lines: string[]): WatchBuildResult => {
    const videos = playlists.reduce((sum, p) => sum + p.videos.length, 0);
    for (const line of [...lines, `mode=${mode} playlists=${playlists.length} videos=${videos}`]) log.info(redact(line, key));
    return { mode, playlists, warnings };
  };

  if (env.mode === 'none' || !client) {
    const missing = missingKeyWarning(env);
    if (missing) warn(missing);
    return finish('none', [], []);
  }

  const dataMode = env.mode;
  // Info lines and per-playlist warnings wait until every call has
  // succeeded, so a global error never leaves fetched lines that contradict
  // mode=none, and lines stay in curated order despite the parallel fetches.
  const lines: string[] = [];
  try {
    const apiPlaylists = await client.listPlaylists(curated.map((c) => c.playlist_id));
    const byId = new Map(apiPlaylists.map((p) => [p.id, p]));
    // A playlist needs a name, and the API title is the only source (UI spec § 3.2).
    const readable = curated.flatMap((c) => {
      const api = byId.get(c.playlist_id);
      return api?.snippet?.title?.trim() ? [{ curated: c, api }] : [];
    });
    const fetched = new Map((await fetchPlaylists(client, readable, dataMode)).map((f) => [f.curated.playlist_id, f]));

    const playlists: WatchPlaylist[] = [];
    for (const c of curated) {
      const f = fetched.get(c.playlist_id);
      if (!f) {
        const why = byId.has(c.playlist_id) ? 'no title in playlists.list' : 'not returned by playlists.list';
        warn(`playlist ${c.playlist_id}: ${why}; leaving it off the page.`);
        lines.push(`skipped ${c.playlist_id}: ${why}`);
        continue;
      }

      let entry: WatchPlaylist;
      let fetchedLine: string | null = null;
      if ('error' in f) {
        warn(`${sentence(f.error.message)} Showing the playlist as failed.`);
        entry = failedPlaylist(c, f.api, dataMode);
      } else {
        const n = f.result;
        entry = n.playlist;
        fetchedLine = `fetched ${c.playlist_id}: ${entry.videos.length} videos (dropped: ${n.dropped}, not embeddable: ${n.droppedBy['not-embeddable'] ?? 0})`;
      }

      const issue = validateEntry(entry);
      if (issue !== null) {
        warn(`playlist ${c.playlist_id} failed the schema check (${issue}); leaving it off the page.`);
        lines.push(`skipped ${c.playlist_id}: failed the schema check`);
        continue;
      }
      playlists.push(entry);
      if (fetchedLine) lines.push(fetchedLine);
    }
    return finish(dataMode, playlists, lines);
  } catch (err) {
    const reason = err instanceof YouTubeError ? (err.reason ?? err.kind) : 'unexpected error';
    const detail = err instanceof YouTubeError
      ? err.message
      : `watch data load failed: ${err instanceof Error ? err.message : String(err)}`;
    warn(`${sentence(detail)} Rendering the empty state.`);
    return finish('none', [], curated.map((c) => `skipped ${c.playlist_id}: global API error (${reason})`));
  }
}
