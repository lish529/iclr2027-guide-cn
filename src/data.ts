/** GitHub Pages serves .gz as a file; tolerate hosts that already decode it. */
export async function fetchJson<T>(path: string, base: string): Promise<T> {
  const r = await fetch(new URL(path, base));
  if (!r.ok) throw new Error(`无法载入数据（${r.status}）`);
  const bytes = new Uint8Array(await r.arrayBuffer());
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    return JSON.parse(await new Response(stream).text()) as T;
  }
  return JSON.parse(new TextDecoder().decode(bytes)) as T;
}
