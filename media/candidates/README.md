# Image candidates

Images being considered for posts or the stock library, each with a `.yml`
record of where it came from and how it may be used. Nothing here is published;
the site build does not read this folder.

**Image files are git-ignored.** Only the `.yml` records and this README are
committed. The repo is public, and stock licences forbid redistributing the
files as they are. Each record keeps the page URL and the file's sha256, so the
image can be downloaded again and checked.

**Licensing:** files here are **not** covered by the repo's MIT or CC-BY-4.0
licences. Each image keeps the licence named in its own `.yml` record.

## Adding one

1. Download the image into `image-inbox/` at the repo root. The folder is
   git-ignored.
2. In Claude Code, run `/image-candidate <image page URL>`. Add
   `for <post-slug>` or a note if you like.

The skill moves the file here and writes the record. It asks for anything it
can't confirm from the page, such as the creator's name.

`/image-candidate list` shows what is here.

## Record fields

See `.claude/skills/image-candidate/SKILL.md`, step 6, for the full template.
The fields that matter most:

| Field | Meaning |
|---|---|
| `status` | `needs-file`, `needs-info`, `candidate`, `approved`, `rejected`, `blocked` or `used` |
| `source.page_url`, `source.creator` | Who made it and where it was found |
| `source.ai_generated` | As the source site labels it: `true`, `false` or `unknown` |
| `source.verified` | Whether the record was checked against the page itself |
| `license.*` | Licence name, URL, whether credit is required, restrictions |
| `credit_line` | The ready-to-use credit text |
| `file.sha256` | The hash of the file as downloaded, for provenance |
| `look.*` | Art or photo, mono or colour, orientation, drawn-in text |
