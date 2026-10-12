import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { formatDuration, parseIsoDuration, spokenDuration } from './duration';

describe('parseIsoDuration (U1)', () => {
  test('minutes and seconds', () => {
    assert.equal(parseIsoDuration('PT22M58S'), 22 * 60 + 58);
  });

  test('hours, days and single parts', () => {
    assert.equal(parseIsoDuration('PT1H2M3S'), 3723);
    assert.equal(parseIsoDuration('PT2H'), 7200);
    assert.equal(parseIsoDuration('PT45S'), 45);
    assert.equal(parseIsoDuration('P1DT2H'), 26 * 3600);
  });

  test('zero', () => {
    assert.equal(parseIsoDuration('PT0S'), 0);
    assert.equal(parseIsoDuration('P0D'), 0);
  });

  test('junk gives null', () => {
    for (const junk of ['', 'P', 'PT', '22:58', 'PT22M58', 'pt22m58s', 'PT1.5S', 'P1W', 'xPT1S', 'PT1Sx']) {
      assert.equal(parseIsoDuration(junk), null, junk);
    }
  });
});

describe('formatDuration (U1)', () => {
  test('m:ss under an hour', () => {
    assert.equal(formatDuration(1378), '22:58');
    assert.equal(formatDuration(65), '1:05');
    assert.equal(formatDuration(0), '0:00');
  });

  test('h:mm:ss from an hour', () => {
    assert.equal(formatDuration(3600), '1:00:00');
    assert.equal(formatDuration(3723), '1:02:03');
    assert.equal(formatDuration(26 * 3600), '26:00:00');
  });
});

describe('spokenDuration (U1)', () => {
  test('plurals', () => {
    assert.equal(spokenDuration(1378), '22 minutes 58 seconds');
    assert.equal(spokenDuration(7322), '2 hours 2 minutes 2 seconds');
  });

  test('singulars', () => {
    assert.equal(spokenDuration(3661), '1 hour 1 minute 1 second');
  });

  test('zero parts are left out, but zero itself is said', () => {
    assert.equal(spokenDuration(3600), '1 hour');
    assert.equal(spokenDuration(3605), '1 hour 5 seconds');
    assert.equal(spokenDuration(120), '2 minutes');
    assert.equal(spokenDuration(0), '0 seconds');
  });
});
