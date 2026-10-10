import { describe, test } from 'node:test';
import assert from 'node:assert/strict';
import { jsonForScript } from './jsonForScript';

describe('jsonForScript', () => {
  test('a closing script tag in a string cannot end the script element', () => {
    const out = jsonForScript({ name: 'Acme </script><img src=x onerror=alert(1)>' });
    assert.ok(!out.includes('</script'), out);
    assert.ok(!out.includes('<'), out);
  });

  test('the escaped output parses back to the same value', () => {
    const value = { title: `a < b </script> c${String.fromCharCode(0x2028)}d`, n: 1, list: ['<x>'] };
    const out = jsonForScript(value);
    assert.ok(!out.includes(String.fromCharCode(0x2028)), out);
    assert.deepEqual(JSON.parse(out), value);
  });

  test('control: plain values are unchanged', () => {
    const value = { '@type': 'Organization', url: 'https://example.org/?a=1&b=2' };
    assert.equal(jsonForScript(value), JSON.stringify(value));
  });
});
