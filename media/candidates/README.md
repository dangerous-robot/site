# Image candidates

Images being considered for posts or the stock library. Each one has:

- a `.yml` record of where it came from and how it may be used;
- a small `.thumb.webp` preview.

Nothing here is published, and the site build does not read this folder.

**Licensing:** files here are **not** covered by the repo's MIT or CC-BY-4.0
licences. Each image keeps the licence named in its own `.yml` record.

## Where each version of an image lives

| Version | Where | In git? | Why |
|---|---|---|---|
| Original download | `media/originals/<id>.<ext>`, on the maintainer's machine | No | The repo is public, and stock licences forbid redistributing files as they are. Originals are also large (often 6000px or more). |
| Preview | `media/candidates/<id>.thumb.webp`, 480px | Yes | Browse candidates on GitHub, in PRs and in cloud sessions. It is re-encoded, metadata is stripped, and the record beside it gives the credit. |
| Record | `media/candidates/<id>.yml` | Yes | Credit, licence, AI label, size, and the sha256 of the original. |
| Web copy, once used | `src/assets/...` (post-images plan) | Yes | The build makes responsive sizes from it. Export it at about 2400px on the long side, with metadata stripped. Never commit the full original. |

**Back up the originals.** `media/originals/` is git-ignored, so deleting the
clone deletes them. Keep a synced copy of that folder (iCloud, Google Drive or
similar). If an original is lost, the record's `page_url` lets you download it
again, and `file.sha256` confirms it's the same file.

**In a cloud session** the laptop's originals aren't there. `/image-candidate
fetch <id>` downloads a working copy from the Pixabay API, which goes up to
1280px on the long side. That is enough for the spotlight, the post page and
link previews. When an image needs the full original, add it from the laptop.

## Adding one

1. Download the image into `image-inbox/` at the repo root. The folder is
   git-ignored.
2. In Claude Code, run `/image-candidate <image page URL>`. Add
   `for <post-slug>` or a note if you like. For your own work, run
   `/image-candidate <file> own <credit> <licence>`.

The skill then:

- moves the original to `media/originals/`;
- writes the preview and the record;
- asks for anything it can't confirm, such as the creator's name.

`/image-candidate list` shows what is here.

## Record fields

See `.claude/skills/image-candidate/SKILL.md`, step 6, for the full template.
The fields that matter most:

| Field | Meaning |
|---|---|
| `status` | `needs-file`, `needs-info`, `candidate`, `approved`, `rejected`, `blocked` or `used` |
| `source.page_url`, `source.creator` | Who made it and where it was found |
| `source.ai_generated` | As the source site labels it: `true`, `false` or `unknown` |
| `source.verified` | Whether the record was checked against the source (page or API) |
| `license.*` | Licence name, URL, whether credit is required, restrictions |
| `credit_line` | The ready-to-use credit text |
| `file.sha256` | The hash of the original as downloaded, for provenance |
| `file.thumb` | The committed preview |
| `look.*` | Art or photo, mono or colour, orientation, drawn-in text |
