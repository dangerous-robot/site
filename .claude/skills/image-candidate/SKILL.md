---
name: image-candidate
description: "Track a downloaded image as a candidate for a post or the stock library, with the credit and licence facts needed to use it. Use when the user passes an image page URL (Pixabay, Unsplash, Pexels, Wikimedia Commons, Openverse, Flickr or any other) to consider for the site, says they downloaded an image to use, or asks to list, approve or reject image candidates. Args: <page-url> [file-path] [for <post-slug>] [notes], or `list`."
---

# Image candidate

Brandon downloads an image and passes its page URL. This skill finds the file,
records where it came from and how it may be used, and files both under
`media/candidates/`. A candidate is not published: nothing under `media/` ships
with the site. Choosing a candidate for a post or the stock library is a later,
separate step.

```
image-inbox/                 # git-ignored drop folder: download here
media/candidates/
  README.md                  # field reference
  <id>.<ext>                 # the image, byte-for-byte as downloaded (git-ignored)
  <id>.yml                   # its record (committed)
```

Image files stay out of git. The repo is public, and stock licences forbid
redistributing their files as they are. The record keeps the page URL and
sha256, so the file can be fetched again and checked. An image only enters git
once it is used on the site, under `src/assets/`.

## Modes

- `<page-url> [file] [for <post-slug>] [notes]`: add a candidate, or update one if the URL or file hash is already recorded.
- `<file> own [credit] [licence]`: Brandon's own work, with no page URL. Use `site: own`, an empty `page_url`, and the creator and licence he states (`verified: true`). Give it a short descriptive id.
- `list`: print a table of every candidate: id, status, site, licence, size, intended post. Read the `*.yml` files; no other steps.
- `approve <id>` / `reject <id> <reason>` / `used <id> <post-slug>`: set `status` (and `status_note` or `used_by`), then stop.

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
candidate anyway with `status: needs-file`, and tell Brandon to drop the file in
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
- **Pixabay:** the pages sit behind a Cloudflare bot check that blocks WebFetch, curl and headless browsers; don't try to get around it. If `PIXABAY_API_KEY` is set, call `https://pixabay.com/api/?key=$PIXABAY_API_KEY&id=<site_id>`. Its `hits[0]` has `user`, `user_id`, `pageURL`, `tags` and the image sizes. The creator URL is `https://pixabay.com/users/<user>-<user_id>/`. The API may not report the AI-generated label; if it doesn't, ask Brandon.
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
default licence, marked unverified). Set `status: needs-info`, and ask Brandon
for the creator name and whether the page shows an AI-generated label. If he
replies in the same session, finish the record.

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
- **Image:** move the file from `image-inbox/` to `media/candidates/<id>.<ext>`. Copy it instead if it came from anywhere else. Never re-encode or resize it: the hash is the provenance.
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
- what's missing (for `needs-info` or `needs-file`, exactly what Brandon has to supply).

Don't commit unless asked. If asked, commit the `.yml` records only (the image
files are git-ignored), one commit per batch:
`chore(media): add image candidates <ids>`.

## Fit with the site

The image guidelines (`docs/image-guidelines.md` once it exists; until then the
"Image guidelines" section of the post-images plan) say what makes a good image
and the minimum sizes. This skill records fit through `flags` and `look`. It
doesn't reject an image on style; Brandon decides at `approve` / `reject`.
