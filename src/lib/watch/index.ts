// Lookups over the /watch client payload: a playlist by slug, a video by
// slug and id. Indexed once per payload array, so every controller that
// asks for the same data shares one index.

interface IndexablePlaylist {
  slug: string;
  videos: readonly { id: string }[];
}

type VideoOf<P extends IndexablePlaylist> = P['videos'][number];

export interface VideoEntry<P extends IndexablePlaylist> {
  playlist: P;
  video: VideoOf<P>;
}

export interface PlaylistIndex<P extends IndexablePlaylist> {
  bySlug(slug: string): P | undefined;
  /** null when the slug is unknown or the video is not in that playlist. */
  findVideo(slug: string, id: string): VideoEntry<P> | null;
}

const cache = new WeakMap<readonly IndexablePlaylist[], PlaylistIndex<IndexablePlaylist>>();

export function indexPlaylists<P extends IndexablePlaylist>(playlists: readonly P[]): PlaylistIndex<P> {
  const hit = cache.get(playlists);
  if (hit) return hit as unknown as PlaylistIndex<P>;
  const entries = new Map(
    playlists.map((playlist) => [playlist.slug, { playlist, videos: new Map(playlist.videos.map((v) => [v.id, v])) }]),
  );
  const index: PlaylistIndex<P> = {
    bySlug: (slug) => entries.get(slug)?.playlist,
    findVideo: (slug, id) => {
      const entry = entries.get(slug);
      const video = entry?.videos.get(id);
      return entry && video ? { playlist: entry.playlist, video } : null;
    },
  };
  cache.set(playlists, index as unknown as PlaylistIndex<IndexablePlaylist>);
  return index;
}
