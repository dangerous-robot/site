// YouTube Data API v3 client for the build-time /watch loader. fetch and sleep
// are injected so tests run offline with a fake clock.
//
// Requests carry only query parameters and an AbortSignal: never a headers
// argument, so never a Referer or Origin. A referrer-restricted key is a
// Google Cloud configuration error, not something to work around here.

export const API_BASE = 'https://www.googleapis.com/youtube/v3';
/** The API's per-request maximum for both maxResults and an id list. */
export const PAGE_SIZE = 50;
const RETRIES = 2;
const RETRY_BASE_MS = 1000;
const TIMEOUT_MS = 15_000;

// fields trims each response to what normalize.ts reads. playlistItems must
// keep nextPageToken or paging silently stops after the first page.
export const FIELDS = {
  playlists: 'items(id,snippet(title,description,channelTitle))',
  playlistItems: 'nextPageToken,items(snippet(position,resourceId(videoId)))',
  videos:
    'items(id,snippet(title,channelTitle,description,publishedAt,liveBroadcastContent,' +
    'thumbnails(medium,high,standard,maxres)),' +
    'contentDetails(duration),status(privacyStatus,uploadStatus,embeddable))',
} as const;

export type ApiCall = 'playlists.list' | 'playlistItems.list' | 'videos.list';

// Response shapes. Every field is optional: the response is untrusted input
// and normalize.ts decides what a usable item is.
export interface ApiThumbnail {
  url?: string;
  width?: number;
  height?: number;
}
export type ApiThumbnailKey = 'default' | 'medium' | 'high' | 'standard' | 'maxres';
export type ApiThumbnails = Partial<Record<ApiThumbnailKey, ApiThumbnail>>;

export interface ApiPlaylist {
  id?: string;
  snippet?: { title?: string; description?: string; channelTitle?: string };
}

export interface ApiPlaylistItem {
  snippet?: { position?: number; resourceId?: { videoId?: string } };
}

export interface ApiVideo {
  id?: string;
  snippet?: {
    title?: string;
    channelTitle?: string;
    description?: string;
    publishedAt?: string;
    liveBroadcastContent?: string;
    thumbnails?: ApiThumbnails;
  };
  contentDetails?: { duration?: string };
  status?: { privacyStatus?: string; uploadStatus?: string; embeddable?: boolean };
}

/** Real fetch satisfies this; tests pass a recording fake. */
export type FetchLike = (url: string, init: { signal: AbortSignal }) => Promise<{ status: number; text(): Promise<string> }>;

export type YouTubeErrorKind = 'quota' | 'key' | 'not-found' | 'forbidden' | 'network' | 'malformed';
export type YouTubeErrorScope = 'global' | 'playlist';

export class YouTubeError extends Error {
  readonly kind: YouTubeErrorKind;
  readonly scope: YouTubeErrorScope;
  readonly call: ApiCall;
  /** 0 when no response arrived. */
  readonly status: number;
  /** error.errors[0].reason from the API, redacted. */
  readonly reason: string | null;
  /** error.message from the API (or the network error text), redacted. */
  readonly apiMessage: string | null;
  readonly playlistId: string | null;
  /** Request URL with the key redacted. */
  readonly url: string;

  constructor(f: {
    kind: YouTubeErrorKind; scope: YouTubeErrorScope; call: ApiCall; status: number;
    reason: string | null; apiMessage: string | null; playlistId: string | null; url: string;
  }) {
    const status = [f.status > 0 ? String(f.status) : '', f.reason ?? f.kind].filter(Boolean).join(' ');
    const where = f.playlistId ? ` for ${f.playlistId}` : '';
    super(`${f.call} failed${where} (${status})${f.apiMessage ? `: ${f.apiMessage}` : ''}`);
    this.name = 'YouTubeError';
    this.kind = f.kind;
    this.scope = f.scope;
    this.call = f.call;
    this.status = f.status;
    this.reason = f.reason;
    this.apiMessage = f.apiMessage;
    this.playlistId = f.playlistId;
    this.url = f.url;
  }
}

/** Removes the key, and any key= query value, from text bound for a log. */
export function redact(text: string, key: string): string {
  // An empty key would make split('') scatter the text, so skip that step.
  const withoutKey = key ? text.split(key).join('[redacted]') : text;
  return withoutKey.replace(/([?&]key=)[^&\s"']*/g, '$1[redacted]');
}

export interface ApiPlaylistItemsPage {
  items: ApiPlaylistItem[];
  /** null on the last page. */
  nextPageToken: string | null;
}

export interface YouTubeClient {
  listPlaylists(ids: string[]): Promise<ApiPlaylist[]>;
  /** One page of up to PAGE_SIZE items; the loader decides whether to fetch the next. */
  listPlaylistItemsPage(playlistId: string, pageToken?: string): Promise<ApiPlaylistItemsPage>;
  listVideos(ids: string[]): Promise<ApiVideo[]>;
}

export interface YouTubeClientOptions {
  key: string;
  fetch: FetchLike;
  sleep?: (ms: number) => Promise<void>;
  timeoutMs?: number;
}

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function chunks<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

interface ApiErrorBody {
  error?: { message?: unknown; errors?: { reason?: unknown }[] };
}

// Reasons that mean the key or the project is unusable, so every call fails.
const KEY_REASONS = new Set(['keyInvalid', 'keyExpired', 'ipRefererBlocked', 'accessNotConfigured']);
// Rate limits clear within seconds, so they are retried like a 5xx; the
// project-wide quota does not.
const RATE_REASONS = new Set(['rateLimitExceeded', 'userRateLimitExceeded']);
const QUOTA_REASONS = new Set(['quotaExceeded', 'dailyLimitExceeded', ...RATE_REASONS]);

const retryable = (status: number, reason: string | null) =>
  status >= 500 || status === 429 || (reason !== null && RATE_REASONS.has(reason));

// A failed batched call leaves every playlist without data. Anything that
// is not a key or quota error from playlistItems.list is about that one
// playlist: a bad page token, a 5xx or a timeout there must not blank the page.
function scopeOf(call: ApiCall): YouTubeErrorScope {
  return call === 'playlistItems.list' ? 'playlist' : 'global';
}

// Key and quota errors are global whatever the call: every other call would
// fail the same way.
function classify(call: ApiCall, status: number, reason: string | null, message: string | null): { kind: YouTubeErrorKind; scope: YouTubeErrorScope } {
  // Reason before status: an invalid key can come back as 400, not 403.
  if (reason !== null && KEY_REASONS.has(reason)) return { kind: 'key', scope: 'global' };
  // A key restricted by referer, IP or API comes back as a plain 403 forbidden.
  if (status === 403 && message && /referer|are blocked/i.test(message)) return { kind: 'key', scope: 'global' };
  if ((reason !== null && QUOTA_REASONS.has(reason)) || status === 429) return { kind: 'quota', scope: 'global' };
  const scope = scopeOf(call);
  if (status === 404) return { kind: 'not-found', scope };
  if (status === 401 || status === 403) return { kind: 'forbidden', scope };
  if (status >= 500) return { kind: 'network', scope };
  return { kind: 'malformed', scope };
}

export function createYouTubeClient(options: YouTubeClientOptions): YouTubeClient {
  const { key, fetch } = options;
  const sleep = options.sleep ?? defaultSleep;
  const timeoutMs = options.timeoutMs ?? TIMEOUT_MS;

  async function request<T>(call: ApiCall, path: string, params: Record<string, string>, playlistId: string | null): Promise<T> {
    const query = new URLSearchParams({ ...params, key });
    const url = `${API_BASE}/${path}?${query}`;
    const safeUrl = redact(url, key);
    const fail = (kind: YouTubeErrorKind, scope: YouTubeErrorScope, status: number, reason: string | null, message: string | null) =>
      new YouTubeError({
        kind, scope, call, status, playlistId, url: safeUrl,
        reason: reason === null ? null : redact(reason, key),
        apiMessage: message === null ? null : redact(message, key),
      });

    for (let attempt = 0; ; attempt++) {
      let status = 0;
      let text = '';
      let networkError: string | null = null;
      try {
        const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
        status = res.status;
        text = await res.text();
      } catch (err) {
        networkError = err instanceof Error ? err.message : String(err);
      }

      // Network error text can include the request URL, so it is redacted
      // and never kept as a cause.
      if (networkError !== null) {
        if (attempt < RETRIES) {
          await sleep(RETRY_BASE_MS * 2 ** attempt);
          continue;
        }
        throw fail('network', scopeOf(call), 0, null, networkError);
      }

      let body: unknown;
      try {
        body = JSON.parse(text);
      } catch {
        body = undefined;
      }

      if (status >= 200 && status < 300) {
        if (!body || typeof body !== 'object' || !Array.isArray((body as { items?: unknown }).items)) {
          throw fail('malformed', scopeOf(call), status, null, 'response is not JSON with an items list');
        }
        return body as T;
      }

      const apiError = (body as ApiErrorBody | undefined)?.error;
      const rawReason = apiError?.errors?.[0]?.reason;
      const reason = typeof rawReason === 'string' ? rawReason : null;
      if (retryable(status, reason) && attempt < RETRIES) {
        await sleep(RETRY_BASE_MS * 2 ** attempt);
        continue;
      }
      const message = typeof apiError?.message === 'string' ? apiError.message : null;
      const { kind, scope } = classify(call, status, reason, message);
      throw fail(kind, scope, status, reason, message);
    }
  }

  async function batched<T>(call: ApiCall, path: string, part: string, fields: string, ids: string[]): Promise<T[]> {
    const out: T[] = [];
    for (const batch of chunks(ids, PAGE_SIZE)) {
      const body = await request<{ items: T[] }>(call, path, { part, fields, id: batch.join(',') }, null);
      out.push(...body.items);
    }
    return out;
  }

  return {
    listPlaylists: (ids) => batched<ApiPlaylist>('playlists.list', 'playlists', 'snippet', FIELDS.playlists, ids),

    async listPlaylistItemsPage(playlistId, pageToken) {
      const params: Record<string, string> = {
        part: 'snippet', fields: FIELDS.playlistItems, playlistId, maxResults: String(PAGE_SIZE),
      };
      if (pageToken) params.pageToken = pageToken;
      const body = await request<{ items: ApiPlaylistItem[]; nextPageToken?: unknown }>(
        'playlistItems.list', 'playlistItems', params, playlistId,
      );
      const next = body.nextPageToken;
      return { items: body.items, nextPageToken: typeof next === 'string' && next ? next : null };
    },

    listVideos: (ids) => batched<ApiVideo>('videos.list', 'videos', 'snippet,contentDetails,status', FIELDS.videos, ids),
  };
}
