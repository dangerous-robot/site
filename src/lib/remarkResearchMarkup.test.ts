import { describe, test, before } from 'node:test';
import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
// Astro's own Markdown processor, so the fixture goes through the same
// raw-HTML handling the site build uses.
import { createMarkdownProcessor } from '@astrojs/markdown-remark';
import remarkResearchMarkup, { isResearchFile, isSafeTarget } from './remarkResearchMarkup';

type Processor = Awaited<ReturnType<typeof createMarkdownProcessor>>;

const HOSTILE = [
  '<script>alert(1)</script>',
  '',
  'Text with <img src=x onerror=alert(1)> inline and <b>bold</b>.',
  '',
  '[run](javascript:alert(1)) and [entity](javascript&#58;alert(1)) and [ref][bad]',
  '',
  '![pic](javascript:alert(1))',
  '',
  '[bad]: javascript:alert(1)',
  '',
  '> a quote with 1 < 2 and a [safe link](https://example.org/x)',
  '',
  'Some **bold** text and a [page link](/research/claims) and [mail](mailto:a@example.org).',
].join('\n');

let processor: Processor;
before(async () => {
  processor = await createMarkdownProcessor({ remarkPlugins: [remarkResearchMarkup] });
});

const research = pathToFileURL(resolve('research/claims/acme/some-claim.md'));
const handWritten = pathToFileURL(resolve('src/content/resources/ai-safety.md'));

describe('remarkResearchMarkup', () => {
  test('research Markdown renders no raw HTML or script-scheme links', async () => {
    const { code } = await processor.render(HOSTILE, { fileURL: research });
    for (const needle of ['<script', '<img', 'onerror', '<b>', 'javascript:', 'alert(1)']) {
      assert.ok(!code.includes(needle), `${needle} in:\n${code}`);
    }
  });

  test('control: ordinary Markdown in the same file still renders', async () => {
    const { code } = await processor.render(HOSTILE, { fileURL: research });
    assert.ok(code.includes('<blockquote>'), code);
    assert.ok(code.includes('1 &#x3C; 2') || code.includes('1 &lt; 2'), code);
    assert.ok(code.includes('<a href="https://example.org/x">safe link</a>'), code);
    assert.ok(code.includes('<a href="/research/claims">page link</a>'), code);
    assert.ok(code.includes('<a href="mailto:a@example.org">mail</a>'), code);
    assert.ok(code.includes('<strong>bold</strong>'), code);
    // The unsafe link's text survives as plain text.
    assert.ok(code.includes('run'), code);
  });

  test('a file with no known path is treated as research', async () => {
    const { code } = await processor.render('<b>x</b>', {});
    assert.ok(!code.includes('<b>'), code);
  });

  test('control: hand-written content outside research/ keeps raw HTML', async () => {
    const { code } = await processor.render('<div class="note">x</div>', { fileURL: handWritten });
    assert.ok(code.includes('<div class="note">'), code);
  });

  test('isResearchFile is based on the path under the repo, not the working directory', () => {
    assert.equal(isResearchFile({ path: resolve('research/sources/2026/x.md') }), true);
    assert.equal(isResearchFile({ path: resolve('researchers/x.md') }), false);
    assert.equal(isResearchFile({ path: resolve('src/content/writing/x.md') }), false);
    assert.equal(isResearchFile({ path: resolve('../research/x.md') }), false);
    assert.equal(isResearchFile({}), true);
    const cwd = process.cwd();
    process.chdir('src');
    try {
      assert.equal(isResearchFile({ path: resolve('../research/claims/a/b.md') }), true);
    } finally {
      process.chdir(cwd);
    }
  });

  test('isSafeTarget', () => {
    for (const bad of ['javascript:1', 'JAVASCRIPT:1', 'java\nscript:1', 'data:text/html,x', 'vbscript:x']) {
      assert.equal(isSafeTarget(bad), false, bad);
    }
    for (const ok of ['https://a.org', 'http://a.org', 'mailto:a@b.org', '/x', '#frag', 'x.md', '']) {
      assert.equal(isSafeTarget(ok), true, ok);
    }
  });
});
