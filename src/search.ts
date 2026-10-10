import type { Filters, Paper } from './types';
const pairs = [
  ['智能体', 'agent'], ['强化学习', 'reinforcement learning', 'rl'],
  ['推理', 'reasoning'], ['多模态', 'multimodal', 'multi-modal'],
  ['世界模型', 'world model'], ['大语言模型', 'llm', 'language model'],
  ['扩散', 'diffusion'], ['图神经网络', 'gnn', 'graph neural'],
  ['联邦学习', 'federated'], ['代码', 'code'], ['量化', 'quantization'],
  ['蒸馏', 'distillation'], ['具身', 'embodied'], ['长上下文', 'long context'],
  ['幻觉', 'hallucination'], ['测试时适应', 'test-time adaptation'],
  ['视觉语言动作', 'vla', 'vision-language-action'], ['因果', 'causal'],
];
export const normalize = (s: string) => s.normalize('NFKC').toLowerCase().replace(/[‐‑–—]/g, '-').replace(/\s+/g, ' ').trim();
export function searchText(p: Paper): string {
  return normalize([p.title,p.titleZh,p.summaryZh,p.primaryArea,p.areaZh,p.subcategory,...p.tags,...p.keywords].join(' '));
}
export function matchesQuery(text: string, query: string): boolean {
  const q = normalize(query);
  if (!q) return true;
  if (text.includes(q)) return true;
  const exact = pairs.find(p => p.includes(q));
  if (exact) return exact.some(t => text.includes(t));
  return q.split(' ').every(word => {
    const aliases = pairs.find(p => p.includes(word));
    return (aliases ?? [word]).some(t => text.includes(t));
  });
}
export function filterPapers(papers: Paper[], f: Filters, matchingIds?: Set<string>): Paper[] {
  return papers.filter(p => p.status === 'active' && (!f.area || p.primaryArea === f.area)
    && (!f.sub || p.subcategory === f.sub) && f.tags.every(t => p.tags.includes(t))
    && (!f.state || p.classification === f.state)
    && (!f.q || (matchingIds ? matchingIds.has(p.id) : matchesQuery(searchText(p), f.q))));
}
export function readFilters(search: string): Filters {
  const p = new URLSearchParams(search);
  return { q:p.get('q') ?? '', area:p.get('area') ?? '', sub:p.get('sub') ?? '',
    tags:[...new Set(p.getAll('tag'))], state:p.get('state') ?? '',
    page:Math.max(1, Math.floor(Number(p.get('page')) || 1)), paper:p.get('paper') ?? '' };
}
export function writeFilters(f: Filters): string {
  const p = new URLSearchParams();
  for (const key of ['q','area','sub','state','paper'] as const) if(f[key]) p.set(key,f[key]);
  f.tags.forEach(t => p.append('tag',t));
  if(f.page>1) p.set('page',String(f.page));
  return p.size ? `?${p}` : '';
}
export function csv(rows: Record<string, unknown>[]): string {
  if(!rows.length) return '\uFEFF';
  const keys = Object.keys(rows[0]);
  const cell = (v: unknown) => {
    let s = Array.isArray(v) ? v.join(' | ') : String(v ?? '');
    if (/^[=+@\-\t\r]/.test(s)) s = "'" + s;
    return `"${s.replaceAll('"','""')}"`;
  };
  return '\uFEFF' + [keys,...rows.map(r=>keys.map(k=>r[k]))].map(row=>row.map(cell).join(',')).join('\r\n');
}
