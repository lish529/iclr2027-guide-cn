import './style.css';
import type { Filters, Manifest, Paper, PaperDetail } from './types';
import { csv, filterPapers, readFilters, writeFilters } from './search';

const $ = <T extends HTMLElement = HTMLElement>(selector: string) => document.querySelector<T>(selector)!;
const escape = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
const icon = (name: string) => ({search:'⌕', arrow:'↗', chevron:'›', book:'▤', close:'×'}[name] ?? name);
const base = new URL(import.meta.env.BASE_URL, location.href).href;
const nf = new Intl.NumberFormat('zh-CN');
const fmt = (n: number | null) => n === null ? '待核验' : nf.format(n);
const date = (s: string) => new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
let manifest: Manifest;
let papers: Paper[] = [];
let filters: Filters = readFilters(location.search);
let matchingIds: Set<string> | undefined;
let searchRequest = 0;
let searchBusy = false;
let searchError = '';
let worker: Worker | null = null;
let pageSize = 20;
const detailCache = new Map<string, Promise<PaperDetail>>();

async function json<T>(path: string): Promise<T> {
  const r = await fetch(new URL(path,base));
  if(!r.ok) throw new Error(`无法载入数据（${r.status}）`);
  return r.json();
}
function detail(p: Paper): Promise<PaperDetail> {
  if(!detailCache.has(p.id)) detailCache.set(p.id,json<PaperDetail>(p.detail).catch(e=>{detailCache.delete(p.id);throw e}));
  return detailCache.get(p.id)!;
}
function syncUrl(replace = false) {
  const url = location.pathname + writeFilters(filters);
  if(url !== location.pathname + location.search) history[replace ? 'replaceState' : 'pushState']({},'',url);
}
function update(patch: Partial<Filters>, replace = false) {
  const oldQ = filters.q;
  filters = {...filters,...patch,page:patch.page ?? 1};
  syncUrl(replace);
  if(oldQ !== filters.q) runSearch();
  renderNavigation(); renderResults();
  $('#query').setAttribute('value',filters.q);
  ($<HTMLSelectElement>('#classification')).value = filters.state;
}
function runSearch() {
  const request = ++searchRequest;
  matchingIds=undefined; searchError='';
  if(!filters.q.trim()) {searchBusy=false; return}
  searchBusy=true;
  if(!worker) {
    worker=new Worker(new URL('./search.worker.ts',import.meta.url),{type:'module'});
    worker.onmessage=event=>{
      if(event.data.request!==searchRequest) return;
      searchBusy=false;
      if(event.data.error) searchError=event.data.error;
      else matchingIds=new Set(event.data.ids);
      renderResults();
    };
    worker.onerror=()=>{
      searchBusy=false; searchError='摘要搜索暂不可用，当前仅匹配标题、导读和标签。';
      worker?.terminate();worker=null;renderResults();
    };
  }
  worker.postMessage({request,q:filters.q,shards:manifest.searchShards,base});
}
function card(p: Paper): string {
  const state = p.classification === 'complete' ? '' : `<span class="badge warn">${p.classification==='review'?'待复核':'待生成中文导读'}</span>`;
  return `<article class="paper" data-id="${escape(p.id)}">
    <div class="paper-top"><span class="eyebrow">${escape(p.areaZh)} <span class="sep">/</span> ${escape(p.subcategory)}</span><span class="paper-number">#${escape(p.number ?? p.id)}</span></div>
    <h3><a href="https://openreview.net/forum?id=${encodeURIComponent(p.id)}" target="_blank" rel="noopener noreferrer">${escape(p.titleZh || p.title)} <span class="external">↗</span></a></h3>
    ${p.titleZh ? `<p class="english-title" lang="en">${escape(p.title)}</p>` : ''}
    <p class="summary">${escape(p.summaryZh || '这篇论文尚未生成中文导读，可展开英文摘要查看。')}</p>
    <div class="tags">${p.tags.map(t=>`<button class="tag ${filters.tags.includes(t)?'selected':''}" data-tag="${escape(t)}">${escape(t)}</button>`).join('')}${state}</div>
    <div class="paper-bottom"><span class="source-note">基于摘要生成 · 暂无公开评分${p.status==='inactive'?' · 已不在有效投稿列表':''}</span><div><button class="text-button" data-share="${escape(p.id)}">分享</button><button class="text-button abstract-toggle" data-abstract="${escape(p.id)}" aria-expanded="false">英文摘要 <span>⌄</span></button></div></div>
    <div class="abstract" hidden></div>
  </article>`;
}
function renderNavigation() {
  const current = filters.area;
  $('#category-tree').innerHTML=`<button class="all-category ${!current?'active':''}" data-area=""><span>全部研究方向</span><span>${fmt(manifest.total)}</span></button>`+
    manifest.areas.map(a=>`<details class="area" ${current===a.name?'open':''}><summary><span class="area-chevron">›</span><button class="area-button ${current===a.name&&!filters.sub?'active':''}" data-area="${escape(a.name)}"><span>${escape(a.label)}</span><span class="count">${fmt(a.count)}</span></button></summary><div class="subcategories">${a.subcategories.map(s=>`<button class="sub-button ${current===a.name&&filters.sub===s.name?'active':''}" data-area="${escape(a.name)}" data-sub="${escape(s.name)}"><span>${escape(s.name)}</span><span>${fmt(s.count)}</span></button>`).join('')}</div></details>`).join('');
  $('#topic-tags').innerHTML=manifest.tags.map(t=>`<button class="topic ${filters.tags.includes(t.name)?'active':''}" data-tag="${escape(t.name)}">${escape(t.name)}<span>${t.count}</span></button>`).join('');
  const chips = [filters.area && {label:manifest.areas.find(a=>a.name===filters.area)?.label??filters.area,type:'area'},
    filters.sub && {label:filters.sub,type:'sub'},...filters.tags.map(t=>({label:t,type:'tag'}))].filter(Boolean) as {label:string;type:string}[];
  $('#filter-chips').innerHTML=chips.map(c=>`<button class="filter-chip" data-remove="${c.type}" data-value="${escape(c.label)}">${escape(c.label)} <span>×</span></button>`).join('');
}
function renderResults() {
  let result=filterPapers(papers,filters,matchingIds);
  const pageCount=Math.max(1,Math.ceil(result.length/pageSize));
  filters.page=Math.min(pageCount,filters.page);
  syncUrl(true);
  const start=(filters.page-1)*pageSize;
  $('#result-count').textContent=searchBusy?'正在搜索英文摘要…':`找到 ${fmt(result.length)} 篇论文`;
  $('#results-label').textContent=filters.q?`“${filters.q}” 的搜索结果`:filters.sub||'探索论文';
  $('#search-status').textContent=searchError;
  for(const id of ['export-json','export-csv']) $<HTMLButtonElement>('#'+id).disabled=searchBusy || !!searchError;
  $('#results').innerHTML=result.length?result.slice(start,start+pageSize).map(card).join(''):
    `<div class="empty"><div>⌕</div><h3>没有找到匹配的论文</h3><p>试试更宽泛的关键词，或移除部分筛选条件。</p><button class="primary" data-reset>清除筛选</button></div>`;
  $('#pagination').innerHTML=result.length?`<span>第 ${start+1}–${Math.min(start+pageSize,result.length)} 篇，共 ${fmt(result.length)} 篇</span><div><button class="page-button" data-page="${filters.page-1}" ${filters.page<=1?'disabled':''} aria-label="上一页">←</button><span>${filters.page} / ${pageCount}</span><button class="page-button" data-page="${filters.page+1}" ${filters.page>=pageCount?'disabled':''} aria-label="下一页">→</button></div>`:'';
}
function toast(message: string) {$('#toast').textContent=message;$('#toast').classList.add('show');setTimeout(()=>$('#toast').classList.remove('show'),3000)}
async function copyLink(paper?: string) {
  const f=paper?{q:'',area:'',sub:'',tags:[],state:'',page:1,paper}:filters;
  const url=location.origin+location.pathname+writeFilters(f);
  try {await navigator.clipboard.writeText(url);toast('链接已复制')} catch {window.prompt('复制这个链接',url)}
}
async function showPaper(id: string) {
  const p=papers.find(p=>p.id===id);
  const dialog=$<HTMLDialogElement>('#paper-dialog');
  $('#dialog-content').innerHTML=p?card(p):'<div class="empty"><h3>当前快照未收录这篇论文</h3><p>可以清除链接中的 paper 参数，返回论文列表。</p></div>';
  if(!dialog.open) dialog.showModal();
}
async function toggleAbstract(button: HTMLElement) {
  const id=button.dataset.abstract!;
  const paper=papers.find(p=>p.id===id)!;
  const article=button.closest('article')!;
  const panel=article.querySelector<HTMLElement>('.abstract')!;
  if(!panel.hidden) {panel.hidden=true;button.setAttribute('aria-expanded','false');return}
  panel.hidden=false;button.setAttribute('aria-expanded','true');panel.textContent='正在载入摘要…';
  try {
    const d=await detail(paper);
    panel.innerHTML=`<h4>ABSTRACT</h4><p lang="en">${escape(d.abstract || '原始记录缺少摘要。')}</p>${d.classificationReason?`<div class="reason"><b>分类依据</b> ${escape(d.classificationReason)}</div>`:''}<p class="official-area">作者填写的研究方向：${escape(d.primaryArea)}</p>`;
  } catch {panel.textContent='摘要载入失败。请收起后重试，或点击标题查看 OpenReview 原文。'}
}
async function exportData(format: 'json'|'csv') {
  if(searchBusy || searchError) {toast('请等待完整摘要搜索完成后再导出');return}
  const btn=$<HTMLButtonElement>(`#export-${format}`);
  btn.disabled=true;
  try {
    const data=await json<PaperDetail[]>('data/all-papers.json');
    const ids=new Set(filterPapers(papers,filters,matchingIds).map(p=>p.id));
    const selected=data.filter(p=>ids.has(p.id));
    const rows=selected.map(p=>({id:p.id,number:p.number,title:p.title,title_zh:p.titleZh,summary_zh:p.summaryZh,
      primary_area:p.primaryArea,subcategory:p.subcategory,tags:p.tags,keywords:p.keywords,
      abstract:p.abstract,classification:p.classification,status:p.status,rating:p.rating,
      openreview:`https://openreview.net/forum?id=${p.id}`,snapshot_kind:manifest.snapshotKind,snapshot_at:manifest.finishedAt}));
    const text=format==='json'?JSON.stringify({manifest,papers:rows},null,2):csv(rows);
    const blob=new Blob([text],{type:format==='json'?'application/json;charset=utf-8':'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;
    a.download=`iclr2027-${manifest.snapshotKind}-${rows.length}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    toast(`已导出当前筛选的 ${rows.length} 篇论文`);
  } catch {toast('导出失败，请检查网络后重试')} finally {btn.disabled=searchBusy || !!searchError}
}
function initEvents() {
  let timer: ReturnType<typeof setTimeout>;
  $('#query').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(()=>update({q:$<HTMLInputElement>('#query').value},true),240)});
  $('#classification').addEventListener('change',()=>update({state:$<HTMLSelectElement>('#classification').value}));
  $('#page-size').addEventListener('change',()=>{pageSize=Number($<HTMLSelectElement>('#page-size').value);update({page:1})});
  document.addEventListener('click',event=>{
    const target=(event.target as HTMLElement).closest<HTMLElement>('button');
    if(!target) return;
    const d=target.dataset;
    if('area' in d){event.preventDefault();update({area:d.area!,sub:d.sub??''});$('#sidebar').classList.remove('mobile-open')}
    if(d.tag) update({tags:filters.tags.includes(d.tag)?filters.tags.filter(t=>t!==d.tag):[...filters.tags,d.tag]});
    if(d.remove==='area') update({area:'',sub:''});
    if(d.remove==='sub') update({sub:''});
    if(d.remove==='tag') update({tags:filters.tags.filter(t=>t!==d.value)});
    if('reset' in d){update({q:'',area:'',sub:'',tags:[],state:''});$<HTMLInputElement>('#query').value=''}
    if(d.page){update({page:Number(d.page)});$('#results-heading').scrollIntoView({behavior:'smooth',block:'start'})}
    if(d.abstract) void toggleAbstract(target);
    if(d.share) void copyLink(d.share);
    if(d.action==='share') void copyLink();
    if(d.action==='menu') $('#sidebar').classList.toggle('mobile-open');
    if(d.action==='close-dialog') $<HTMLDialogElement>('#paper-dialog').close();
  });
  $('#export-json').addEventListener('click',()=>void exportData('json'));
  $('#export-csv').addEventListener('click',()=>void exportData('csv'));
  $('#paper-dialog').addEventListener('close',()=>{filters.paper='';syncUrl()});
  window.addEventListener('popstate',()=>{
    filters=readFilters(location.search);$<HTMLInputElement>('#query').value=filters.q;
    $<HTMLSelectElement>('#classification').value=filters.state;runSearch();renderNavigation();renderResults();
    if(filters.paper) void showPaper(filters.paper);
    else $<HTMLDialogElement>('#paper-dialog').close();
  });
}
function shell() {
  const complete=manifest.snapshotKind==='complete';
  const progress=manifest.total?Math.round(100*manifest.classified/manifest.total):0;
  $('#app').innerHTML=`
    <header class="topbar"><a class="brand" href="${escape(import.meta.env.BASE_URL)}"><span class="brand-icon">▥</span><b>Paper Atlas</b><span class="brand-divider"></span><span>ICLR 2027</span></a><div class="toplinks"><a href="${manifest.sourceUrl}" target="_blank" rel="noopener">OpenReview ↗</a><button class="text-button" data-action="share">分享导航 ↗</button><span class="edition">中文导读</span></div></header>
    <div class="layout"><aside id="sidebar" class="sidebar"><div class="sidebar-title">研究方向 <span>${manifest.areas.length}</span></div><nav id="category-tree" aria-label="论文分类"></nav><div class="sidebar-foot"><div class="mini-mark">◉</div><p>从一个问题出发，<br>找到值得阅读的论文。</p><small>分类依据：官方方向 + 英文摘要<br>AI 生成导读，请结合原文阅读。</small></div></aside>
    <main><section class="hero"><div class="hero-copy"><div class="hero-kicker"><span class="live-dot"></span> THE FIFTEENTH ICLR <span>/</span> 2027</div><h1>让研究，更容易被发现<span>。</span></h1><p>探索 ICLR 2027 投稿，用中文快速理解每一篇论文。<br>从研究方向到交叉主题，找到你的下一条研究线索。</p><div class="hero-meta">有效投稿 · 基于摘要分类 · ${complete?'已核验快照':'样本预览'}</div></div><div class="hero-graphic" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="orbit orbit-three"></div><div class="graphic-center">ICLR<span>2027</span></div><i class="node n1"></i><i class="node n2"></i><i class="node n3"></i><i class="node n4"></i><span class="graphic-label l1">REASONING</span><span class="graphic-label l2">REPRESENTATION</span><span class="graphic-label l3">DISCOVERY</span></div></section>
    <section class="notice ${complete?'verified':''}" aria-label="数据覆盖说明"><span class="notice-symbol">${complete?'✓':'i'}</span><div><strong>${complete?'元数据全量核验通过':'这是可用的样本预览，尚未完成全量采集'}</strong><p>${escape(manifest.note || (complete?'分类进度单独统计；暂无公开评分，不进行质量排名。':'批量接口需要 OpenReview 验证；以下数量仅对应已读取样本，不代表整届投稿。'))}</p></div></section>
    <section class="stats" aria-label="数据统计"><div class="stat"><span>当前有效投稿总数</span><strong>${fmt(manifest.officialCount)}</strong><small>${complete?'OpenReview 核验结果':'接口恢复后核验'}</small></div><div class="stat"><span>${complete?'已收录论文':'已读取样本'}</span><strong>${fmt(manifest.total)}<em>篇</em></strong><small>缺摘要 ${manifest.missingAbstract} · 抓取失败 ${manifest.failures}</small></div><div class="stat"><span>中文分类已完成</span><strong>${fmt(manifest.classified)}<em>篇</em></strong><small>待处理 ${manifest.pending} · 待复核 ${manifest.review}</small></div><div class="stat"><span>已覆盖研究方向</span><strong>${manifest.areas.length}<em>类</em></strong><small>${complete?'收录论文':'样本内'}完成度 ${progress}%</small></div></section>
    <section class="explore"><div class="section-heading"><span class="section-number">01 /</span><h2>按主题探索</h2><span class="hint">可多选，显示同时匹配的论文</span></div><div id="topic-tags" class="topics"></div></section>
    <section class="library"><div class="section-heading library-heading"><span class="section-number">02 /</span><h2>论文库</h2><span class="snapshot-time">采集于 ${date(manifest.finishedAt)}（北京时间）</span></div>
    <div class="search-bar"><span class="search-icon">⌕</span><input id="query" type="search" placeholder="搜索中文 / 英文标题、摘要、关键词…" aria-label="搜索论文" value="${escape(filters.q)}" autocomplete="off"/><kbd>/</kbd></div>
    <div class="toolbar"><div><button class="mobile-menu secondary" data-action="menu">研究方向 ☰</button><label class="sr-only" for="classification">分类状态</label><select id="classification"><option value="">全部分类状态</option value="complete">已完成</option><option value="review">待复核</option><option value="pending">待处理</option></select><button class="text-button clear" data-reset>清除筛选</button></div><div class="export"><span>导出当前结果</span><button id="export-json" class="secondary">JSON ↓</button><button id="export-csv" class="secondary">CSV ↓</button></div></div>
    <div id="filter-chips" class="filter-chips"></div><p id="search-status" class="search-error" role="status"></p>
    <div id="results-heading" class="results-heading"><h2 id="results-label">探索论文</h2><span id="result-count" aria-live="polite"></span><label class="page-size"><select id="page-size" aria-label="每页论文数"><option value="20">20 篇 / 页</option><option value="50">50 篇 / 页</option><option value="100">100 篇 / 页</option></select></label></div><div id="results"></div><div id="pagination" class="pagination"></div></section>
    <footer><span>ICLR 2027 · 中文论文导航</span><p>元数据来自 OpenReview。中文内容基于摘要生成；投稿状态不代表录用结果。</p><a href="./data/manifest.json" target="_blank">查看数据快照 ↗</a></footer></main></div>
    <dialog id="paper-dialog"><button class="dialog-close" data-action="close-dialog" aria-label="关闭论文详情">×</button><div id="dialog-content"></div></dialog><div id="toast" role="status"></div>`;
  document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA','SELECT'].includes((e.target as HTMLElement).tagName)){e.preventDefault();$('#query').focus()}});
}
async function init() {
  try {
    [manifest,papers]=await Promise.all([json<Manifest>('data/manifest.json'),json<Paper[]>('data/index.json')]);
    shell();initEvents();runSearch();renderNavigation();renderResults();
    $<HTMLSelectElement>('#classification').value=filters.state;
    if(filters.paper) void showPaper(filters.paper);
  } catch(e) {
    $('#app').innerHTML=`<div class="boot"><h1>论文索引暂时无法载入</h1><p>${escape(e instanceof Error?e.message:e)}</p><button class="primary" id="retry">重新加载</button></div>`;
    $('#retry').onclick=()=>location.reload();
  }
}
void init();
