/// <reference lib="webworker" />
import { matchesQuery, normalize } from './search';
import { fetchJson } from './data';
let index: {id: string; text: string}[] = [];
let loading: Promise<void> | null = null;
let latest = 0;
let completed = 0;
self.onmessage = async (event: MessageEvent<{request: number; q: string; shards: string[]; base: string}>) => {
  const {request,q,shards,base} = event.data;
  latest = request;
  try {
    if(!loading) loading = (async () => {
      index = []; completed = 0;
      let cursor = 0;
      await Promise.all(Array.from({length:Math.min(3,shards.length)}, async () => {
        while(cursor < shards.length) {
          const path = shards[cursor++];
          const rows = await fetchJson<{id:string;text:string}[]>(path,base);
          index.push(...rows.map(p=>({id:p.id,text:normalize(p.text)})));
          self.postMessage({request:latest,progress:++completed,total:shards.length});
        }
      }));
    })();
    await loading;
    if(request !== latest) return;
    self.postMessage({request, ids:index.filter(p=>matchesQuery(p.text,q)).map(p=>p.id)});
  } catch(e) {
    // Terminate/recreate the worker on error so an old in-flight loader cannot mutate a retry.
    self.postMessage({request,error:e instanceof Error ? e.message : '搜索失败'});
  }
};
