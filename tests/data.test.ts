import { test } from 'node:test';
import assert from 'node:assert/strict';
import { gzipSync } from 'node:zlib';
import { fetchJson } from '../src/data';

test('compressed JSON and already-decoded hosting responses preserve Chinese and abstracts', async () => {
  const input = [{id:'a',title:'中文标题',abstract:'line one\nline two'}];
  const realFetch = globalThis.fetch;
  try {
    for(const bytes of [gzipSync(JSON.stringify(input)), Buffer.from(JSON.stringify(input))]) {
      globalThis.fetch = async () => new Response(bytes);
      assert.deepEqual(await fetchJson('data/x.json.gz','https://example.org/guide/'),input);
    }
    globalThis.fetch = async () => new Response('missing',{status:404});
    await assert.rejects(fetchJson('missing','https://example.org/'),/404/);
  } finally {globalThis.fetch = realFetch;}
});
