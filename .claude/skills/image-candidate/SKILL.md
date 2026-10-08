---
name: image-candidate
description: "Track a downloaded image as a candidate for a post or the stock library, with the credit and licence facts needed to use it. Use when the user passes an image page URL (Pixabay, Unsplash, Pexels, Wikimedia Commons, Openverse, Flickr or any other) to consider for the site, says they downloaded an image to use, or asks to list, approve or reject image candidates. Args: <page-url> [file-path] [for <post-slug>] [notes], or `list`."
---

# Image candidate

The user downloads an image and passes its page URL. This skill finds the file,
records where it came from and how it may be used, and files both under
`media/candidates/`. A candidate is not published: nothing under `media/` ships
with the site. Choosing a candidate for a post or the stock library is a later,
separate step.

```
image-inbox/                 # git-ignored drop folder: download here
media/originals/<id>.<ext>   # git-ignored: the original, byte-for-byte as downloaded
media/candidates/
  README.md                  # field reference and the image lifecycle
  <id>.yml                   # its record (committed)
  <id>.thumb.webp            # 480px preview (committed)
src/assets/posts/<id>.jpg    # web copy, once the image is used on a post (committed)
```

The repo is public, and stock licences forbid redistributing files as they
are. So originals stay out of git; they stay on the user's machine. Git holds a
small re-encoded preview and the record. The record keeps the page URL and
the original's sha256, so the original can be fetched again and checked. A
web-sized copy enters git only once the image is used on the site, under
`src/assets/`.

## Modes

- `<page-url> [file] [for <post-slug>] [notes]`: add a candidate, or update one if the URL or file hash is already recorded.
- `<file> own [credit] [licence]`: the user's own work, with no page URL. Use `site: own`, an empty `page_url`, and the creator and licence they state (`verified: true`). Give it a short descriptive id.
- `fetch <id>`: put a working copy of the original in `media/originals/`, for example in a cloud session where the laptop's files aren't available. For Pixabay, download the API's `largeImageURL` (1280px on the long side; the free API has nothing larger). Other sites: use the page's download link where the licence allows it, otherwise ask the user. Save it as `<id>.<ext>`, unless the laptop original is already there. A fetched copy's hash won't match `file.sha256`; don't overwrite the record.
- `list`: print a table of every candidate: id, status, site, licence, size, intended post. Read the `*.yml` files; no other steps.
- `approve <id>`: re-run the step 5 licence check first. Approve only from `candidate`, or from `blocked` once `license.permission` says where written permission is kept. Refuse, naming what's missing, when the file or credit is incomplete: status `needs-file` or `needs-info`, `source.verified: false`, or a `credit_line` that still has a `<placeholder>`.
- `reject <id> <reason>`: from any status.
- `used <id> <post-slug>`: only from `approved`. Export the web copy with
  `uv run --with pillow python3 .claude/skills/image-candidate/export_web.py media/originals/<id>.<ext> <id>`.
  It writes `src/assets/posts/<id>.jpg` (`.png` with transparency): cropped to the subject when the image sits on a flat background, 2400px on the long side at most, metadata stripped. Then add `image` to the post's frontmatter (`src`, `alt`, `credit`, and `invert_in_dark: true` for black art on white) and list the image on `/credits`.
  The crop and size are the same for every image. Don't hand-tune a crop for one post; if the rule gives a poor result, change the rule.

  `approve` and `reject` set `status` (and `status_note`), then stop. `used` sets `status` and `used_by` after the steps above.

## Steps for adding

### 1. Parse the URL

Get the site, and the site's own image id when there is one:

| Site | URL shape | Id |
|---|---|---|
| Pixabay | `pixabay.com/{photos,illustrations,vectors}/<slug>-<id>/` | trailing number |
| Unsplash | `unsplash.com/photos/<slug>-<id>` | trailing token |
| Pexels | `pexels.com/photo/<slug>-<id>/` | trailing number |
| Wikimedia Commons | `commons.wikimedia.org/wiki/File:<name>` | file name |
| Openverse | `openverse.org/image/<uuid>` | uuid |
| Flickr | `flickr.com/photos/<user>/<id>` | number |

Other sites: use the hostname as `site` and leave `site_id` empty.

### 2. Find the file

Look in this order and use the first match:

1. A path given in the arguments, or an image attached in the chat that the harness saved to disk (it says the path).
2. A file in `image-inbox/` whose name contains the site id. Pixabay names downloads like `arrows-10142347_1920.png`.
3. The only image in `image-inbox/` newer than every recorded candidate.

If several files could match, ask which one. If none matches, record the
candidate anyway with `status: needs-file`, and tell the user to drop the file in
`image-inbox/` and run the skill again with the same URL.

Run `mkdir -p image-inbox` first so the folder exists on a fresh clone.

### 3. Inspect the file

```bash
python3 .claude/skills/image-candidate/inspect_image.py <file>
```

This prints the format, width, height, orientation, bytes, sha256 and
guideline flags (too small, portrait, HEIC, over 5 MB). If the sha256 matches an
existing record, update that record instead of adding a new one.

For a photo, also check the EXIF for GPS (Pillow: `Image.open(f).getexif().get_ifd(0x8825)`). Flag any location data, so it is stripped before the photo is used on the site.

Then look at the image (Read it) and fill in:
- `kind`: `art` (drawn, flat or graphic) or `photo`.
- `palette`: `mono` (black and white) or `color`.
- `has_text`: true when words or numbers are drawn into the image.
- `alt_draft`: a first alt text, under about 125 characters.

### 4. Get the credit and licence

Fetch the page (WebFetch, or `curl` for an API) and read: title, creator name and profile URL, licence name and URL, upload date, and whether the site labels the image AI-generated. Useful endpoints:

- **Wikimedia Commons:** `https://commons.wikimedia.org/w/api.php?action=query&titles=File:<name>&prop=imageinfo&iiprop=extmetadata|url&format=json`. `extmetadata` has `Artist`, `LicenseShortName`, `LicenseUrl` and `Credit`.
- **Pixabay:** the pages sit behind a Cloudflare bot check that blocks WebFetch, curl and headless browsers; don't try to get around it. Use the API with `PIXABAY_API_KEY`: `curl -s "https://pixabay.com/api/?key=$PIXABAY_API_KEY&id=<site_id>"` in Bash. Never use WebFetch for this call, and never print or record the URL with the key filled in. Clients other than curl need their own User-Agent header (Python's default gets a 403). `hits[0]` has:
  - `user` and `user_id`: the creator URL is `https://pixabay.com/users/<user>-<user_id>/`;
  - `isAiGenerated`: goes into `ai_generated`;
  - `noAiTraining` and `isLowQuality`: flag these when true;
  - `imageWidth` and `imageHeight`: the original's size;
  - `tags`, `name` and `pageURL`.
  
  A record checked this way gets `verified: true`. The full-size image (`largeImageURL`) is on `cdn.pixabay.com`, which needs its own network allowance; without it, use the file the user downloaded.
- **Openverse:** `https://api.openverse.org/v1/images/<uuid>/` has `creator`, `license`, `license_version`, `license_url` and `attribution`.

Platform defaults, as of 2026-10. Re-check them against the page; the page wins.

| Site | Licence | Attribution | Notes |
|---|---|---|---|
| Pixabay | Pixabay Content License, `https://pixabay.com/service/license-summary/` | not required | No selling of unaltered copies and no redistribution as stock. Pixabay labels AI-generated uploads. Credit form: "Image by <creator> from Pixabay". |
| Unsplash | Unsplash License, `https://unsplash.com/license` | not required | No selling of unaltered copies. Credit form: "Photo by <creator> on Unsplash". |
| Pexels | Pexels License, `https://www.pexels.com/license/` | not required | No selling of unaltered copies. Credit form: "Photo by <creator> from Pexels". |
| Commons, Flickr, Openverse | per image | per licence | Read the licence on each image. |

**Never invent a creator or a licence.** If the page can't be fetched (blocked,
login wall, error), fill in what the URL proves (site, id, the platform's
default licence, marked unverified). Set `status: needs-info`, and ask the user
for the creator name and whether the page shows an AI-generated label. If they
reply in the same session, finish the record.

### 5. Licence check

| Licence | Result |
|---|---|
| Own work, public domain, CC0, CC-BY | ok |
| Pixabay, Unsplash, Pexels platform licences | ok. These aren't Creative Commons licences, so the image can't be relicensed under the site's CC-BY-4.0. Record it; no further action. |
| CC-BY-SA | ok, with a flag: anything derived from the image must stay under BY-SA. |
| Any NC or ND, "all rights reserved", editorial-only, or unknown | `status: blocked`, unless written permission is recorded in `permission`. |

Separately, flag (don't block) an image the site labels AI-generated, or one
that shows a real person's face, a company logo or a trademark.

### 6. File it

- **Id:** the page slug, lower-case kebab, without the site id (`arrows-colorful-direction-paths`). Add `-<site_id>` only if the id is already taken.
- **Original:** move the file from `image-inbox/` to `media/originals/<id>.<ext>`. Copy it instead if it came from anywhere else. Never re-encode or resize it: the hash is the provenance.
- **Thumbnail:** run `uv run --with pillow python3 .claude/skills/image-candidate/make_thumb.py media/originals/<id>.<ext> <id>`. This writes `media/candidates/<id>.thumb.webp`: 480px on the long side, metadata stripped. Skip the thumbnail and record `thumb: ""` for an SVG, and for any image whose step 5 result is `blocked`: a preview of an image the site may not use is still a copy of it.
- **Record:** write `media/candidates/<id>.yml` with every field in the template below, in this order. Leave a field empty rather than guessing.

```yaml
id: arrows-colorful-direction-paths
status: candidate          # needs-file | needs-info | candidate | approved | rejected | blocked | used
status_note: ""
title: Arrows Colorful Direction
source:
  site: pixabay
  site_id: "10142347"
  page_url: https://pixabay.com/illustrations/arrows-colorful-direction-paths-10142347/
  creator: ""
  creator_url: ""
  uploaded: ""
  ai_generated: unknown    # true | false | unknown, as the site labels it
  verified: false          # true once the page itself was read
license:
  name: Pixabay Content License
  url: https://pixabay.com/service/license-summary/
  attribution_required: false
  restrictions: No selling unaltered copies; no redistribution as stock.
  permission: ""           # where written permission is kept, if any
credit_line: "Image by <creator> from Pixabay"
file:
  name: arrows-colorful-direction-paths.webp
  thumb: arrows-colorful-direction-paths.thumb.webp
  original_name: 1.webp
  format: webp
  width: 1604
  height: 2000
  bytes: 349126
  sha256: 5eae113f…
  downloaded: 2026-10-07
look:
  kind: art                # art | photo
  palette: color           # mono | color
  orientation: portrait
  has_text: false
alt_draft: ""
intended_for: []           # post slugs, or "stock"
used_by: []
flags: []                  # from inspect_image.py, plus licence and content flags
notes: ""
```

### 7. Report

Keep the reply to five lines or fewer:

- the id and status;
- the credit line;
- the licence result;
- the flags, if any;
- what's missing (for `needs-info` or `needs-file`, exactly what the user has to supply).

Don't commit unless asked. If asked, commit the `.yml` record for each image, and its
`.thumb.webp` when step 6 made one (originals are git-ignored), one commit per batch:
`chore(media): add image candidates <ids>`.

## Fit with the site

The image guidelines (`docs/image-guidelines.md` once it exists; until then the
"Image guidelines" section of the post-images plan) say what makes a good image
and the minimum sizes. This skill records fit through `flags` and `look`. It
doesn't reject an image on style; the user decides at `approve` / `reject`.
