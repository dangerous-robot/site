/**
 * JSON for an inline `<script>` body (JSON-LD, config payloads).
 *
 * The HTML parser ends a script element at the first `</script`, whatever the
 * JSON quoting says, so a `<` inside a string (a claim title, an entity name)
 * could close the block early. `<` is the same character to JSON.parse
 * and to JSON-LD consumers, so escaping every `<` costs nothing. U+2028 and
 * U+2029 are escaped because older JavaScript parsers treat them as line ends.
 */
const LINE_SEPARATORS = new RegExp(`[${String.fromCharCode(0x2028)}${String.fromCharCode(0x2029)}]`, 'g');

export function jsonForScript(value: unknown): string {
  return JSON.stringify(value)
    .replace(/</g, '\\u003c')
    .replace(LINE_SEPARATORS, (c) => `\\u${c.charCodeAt(0).toString(16)}`);
}
