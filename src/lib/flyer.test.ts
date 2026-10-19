import { describe, test, beforeEach, afterEach } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { listPetitionActions, flyerFingerprint, flyerState, writeFlyerManifest, pdfPageCount, flyerPdfPath, flyerPagePath, petitionUrl } from './flyer';

let actions: string;
let flyers: string;
beforeEach(() => {
  actions = mkdtempSync(join(tmpdir(), 'actions-'));
  flyers = mkdtempSync(join(tmpdir(), 'flyers-'));
  writeFileSync(join(actions, 'pledge.md'), '---\ntitle: P\npetition: x\n---\nbody\n');
  writeFileSync(join(actions, 'draft.md'), '---\ntitle: D\npetition: y\ndraft: true\n---\n');
  writeFileSync(join(actions, 'note.md'), '---\ntitle: N\n---\nno petition\n');
});
afterEach(() => { rmSync(actions, { recursive: true }); rmSync(flyers, { recursive: true }); });

describe('flyer helpers', () => {
  test('listPetitionActions keeps files with a petition key and reads draft and text', () => {
    const list = listPetitionActions(actions);
    assert.deepEqual(list.map((a) => [a.slug, a.draft]).sort(), [['draft', true], ['pledge', false]]);
    assert.equal(list.find((a) => a.slug === 'pledge')!.text, '---\ntitle: P\npetition: x\n---\nbody\n');
  });
  test('listPetitionActions rejects a bad file name and a front matter slug', () => {
    writeFileSync(join(actions, 'Bad_Name.md'), '---\ntitle: B\npetition: z\n---\n');
    assert.throws(() => listPetitionActions(actions), /Bad_Name\.md/);
    rmSync(join(actions, 'Bad_Name.md'));
    writeFileSync(join(actions, 'aliased.md'), '---\ntitle: A\npetition: z\nslug: other\n---\n');
    assert.throws(() => listPetitionActions(actions), /aliased\.md/);
  });
  test('petitionUrl builds the slashless page url and rejects a bad slug', () => {
    assert.equal(petitionUrl('p'), 'https://dangerousrobot.org/petitions/p');
    assert.throws(() => petitionUrl('../x'));
    assert.throws(() => petitionUrl('Upper'));
  });
  test('flyerFingerprint changes with the text, the url or a template, and is 64 hex chars', () => {
    const tpl = join(actions, 'tpl.astro');
    writeFileSync(tpl, 'a');
    const base = flyerFingerprint('t', 'https://x/p', [tpl]);
    assert.match(base, /^[0-9a-f]{64}$/);
    assert.notEqual(base, flyerFingerprint('t ', 'https://x/p', [tpl]));
    assert.notEqual(base, flyerFingerprint('t', 'https://x/p/', [tpl]));
    writeFileSync(tpl, 'b');
    assert.notEqual(base, flyerFingerprint('t', 'https://x/p', [tpl]));
  });
  test('flyerState is missing without a pdf or manifest, current after writeFlyerManifest, stale on a new fingerprint', () => {
    assert.equal(flyerState('pledge', 'f1', flyers), 'missing');
    writeFileSync(join(flyers, 'pledge.pdf'), '%PDF-1.4');
    assert.equal(flyerState('pledge', 'f1', flyers), 'missing');
    writeFlyerManifest({ slug: 'pledge', url: 'https://x/p', fingerprint: 'f1', generated: '2026-10-18T00:00:00Z' }, flyers);
    assert.equal(flyerState('pledge', 'f1', flyers), 'current');
    assert.equal(flyerState('pledge', 'f2', flyers), 'stale');
  });
  test('pdfPageCount counts page objects, not the Pages tree', () => {
    const one = Buffer.from('%PDF-1.4\n1 0 obj << /Type /Pages /Kids [2 0 R] >>\n2 0 obj << /Type /Page /Parent 1 0 R >>\n');
    const two = Buffer.concat([one, Buffer.from('3 0 obj << /Type /Page /Parent 1 0 R >>\n')]);
    assert.equal(pdfPageCount(one), 1);
    assert.equal(pdfPageCount(two), 2);
  });
  test('paths', () => {
    assert.equal(flyerPdfPath('p'), '/flyers/p.pdf');
    assert.equal(flyerPagePath('p'), '/petitions/p/flyer');
  });
});
