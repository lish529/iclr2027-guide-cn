import {test} from 'node:test';
import assert from 'node:assert/strict';
import {csv,filterPapers,matchesQuery,normalize,readFilters,searchText,writeFilters} from '../src/search';
import type {Paper} from '../src/types';
const make=(id:string,patch:Partial<Paper>={}):Paper=>({id,number:1,title:'A world model for robots',titleZh:'机器人世界模型',summaryZh:'学习动作的因果效应',primaryArea:'causal reasoning',areaZh:'因果推理',subcategory:'世界模型',tags:['世界模型','因果'],keywords:['world model'],status:'active',classification:'complete',modified:null,fingerprint:'a',detail:'a.json',rating:null,...patch});

test('bilingual semantic aliases, literal punctuation and all query terms',()=>{
  const text=normalize('Agent performs reinforcement learning; A Window: (Test)');
  assert.ok(matchesQuery(text,'智能体'));
  assert.ok(matchesQuery(text,'强化学习'));
  assert.ok(matchesQuery(text,'Agent learning'));
  assert.ok(matchesQuery(text,'A Window: (Test)'));
  assert.equal(matchesQuery(text,'Agent volcano'),false);
});
test('area, subcategory, all selected tags and active status combine',()=>{
  const data=[make('a'),make('b',{tags:['世界模型']}),make('c',{status:'inactive'})];
  const filters={...readFilters(''),area:'causal reasoning',sub:'世界模型',tags:['世界模型','因果']};
  assert.deepEqual(filterPapers(data,filters).map(p=>p.id),['a']);
});
test('abstract worker matches are authoritative and apply alongside facets',()=>{
  const data=[make('a'),make('b',{primaryArea:'other'})];
  const filters={...readFilters(''),q:'phrase-only-in-abstract',area:'causal reasoning'};
  assert.equal(filterPapers(data,filters).length,0);
  assert.deepEqual(filterPapers(data,filters,new Set(['a','b'])).map(p=>p.id),['a']);
});
test('share URL round trips Chinese, repeated tags, special chars and paper ID',()=>{
  const filters={q:'A&B + 世界',area:'graphs & geometry',sub:'世界模型',tags:['因果','世界模型'],state:'review',page:3,paper:'abc-123'};
  assert.deepEqual(readFilters(writeFilters(filters)),filters);
  assert.equal(readFilters('?page=-9').page,1);
  assert.equal(readFilters('?page=NaN').page,1);
});
test('CSV preserves quotes/newlines and protects spreadsheet formula interpretation',()=>{
  const result=csv([{title:'=1+1',abstract:'a,"b"\n第二行',tags:['因果','LLM'],rating:null}]);
  assert.ok(result.startsWith('\uFEFF'));
  assert.ok(result.includes('"\'=1+1"'));
  assert.ok(result.includes('"a,""b""\n第二行"'));
  assert.ok(result.includes('因果 | LLM'));
});
test('unclassified papers remain searchable by title and keyword',()=>{
  assert.ok(matchesQuery(searchText(make('x',{titleZh:'',summaryZh:'',classification:'pending'})),'world model'));
});

test('short bilingual acronyms cannot match inside unrelated words', () => {
  assert.equal(matchesQuery('world models for distribution learning', '强化学习'), false);
  assert.equal(matchesQuery('rlhf improves policy learning', '强化学习'), true);
  assert.equal(matchesQuery('gnns and graph neural networks', '图神经网络'), true);
});
