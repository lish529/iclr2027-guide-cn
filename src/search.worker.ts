/// <reference lib="webworker" />
import { matchesQuery, normalize } from './search';
let index: {id: string; text: string}[] = [];
let loading: Promise<void> | null = null;
self.onmessage = async (event: MessageEvent<{request: number; q: string; shards: string[]; base: string}>) => {
  const {request,q,shards,base} = event.data;
  try {
    if(!loading) loading = (async () => {
      const entries: {id: string; text: string}[] = [];
      for(const path of shards) {
        const r = await fetch(new URL(path,base));
        if(!r.ok) throw new Error('摘要搜索索引载入失败');
        entries.push(...await r.json());
      }
      index = entries.map(p=>({id:p.id,text:normalize(p.text)}));
    })();
    await loading;
    self.postMessage({request, ids:index.filter(p=>matchesQuery(p.text,q)).map(p=>p.id)});
  } catch(e) {
    loading=null;
    self.postMessage({request,error:e instanceof Error ? e.message : '搜索失败'});
  }
};
