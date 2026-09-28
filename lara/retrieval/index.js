'use strict';
const {queryTerms}=require('../language');
function rank(index, query, lang, disabled=new Set(), limit=5) {
  const terms=queryTerms(query,lang); const q=query.toLocaleLowerCase();
  if(!terms.length) return [];
  const scored=(index.resources||[]).filter(r=>!disabled.has(r.resource_id)).map(r=>{
    const title=(r.title||'').toLocaleLowerCase(), meta=[...(r.keywords||[]),...(r.topics||[]),r.architecture||'',r.parent_standard||'',r.module||''].join(' ').toLocaleLowerCase();
    let score=0; for(const term of terms){const t=term.toLocaleLowerCase(); if(title.includes(t)) score+=t.length<4?5:8; if(meta.includes(t))score+=3;
      let best=0; for(const c of (r.chunks||[])){const cl=c.text.toLocaleLowerCase(); if(cl.includes(t))best=Math.max(best,Math.min(3,1+cl.split(t).length*0.25));} score+=best; }
    const acr=(r.title||'').match(/\(([A-Z][A-Z0-9-]{1,12})\)/)?.[1]; if(acr&&q.includes(acr.toLocaleLowerCase()))score+=20;
    if(score>0&&r.resource_type==='Architecture')score+=1;
    return {resource:r,score};
  }).sort((a,b)=>b.score-a.score||a.resource.canonical_url.localeCompare(b.resource.canonical_url));
  const matches=scored.filter(x=>x.score>0);const selected=matches.slice(0,limit);const byId=new Map(scored.map(x=>[x.resource.resource_id,x]));const expanded=new Map(selected.map(x=>[x.resource.resource_id,x]));
  // Expand only OOF registry-declared relationships from strong source matches.
  for(const seed of selected.slice(0,3))for(const edge of seed.resource.related_resources||[]){if(edge.relationship&&!['relatedDocument','parentResource','moduleFlow','crossArchitectureInterface'].includes(edge.relationship))continue;const candidate=byId.get(edge.resource_id);if(candidate&&!expanded.has(edge.resource_id))expanded.set(edge.resource_id,{...candidate,score:candidate.score+0.5,related_via:seed.resource.resource_id});}
  return [...expanded.values()].sort((a,b)=>b.score-a.score||a.resource.canonical_url.localeCompare(b.resource.canonical_url)).slice(0,Math.min(limit+3,8));
}
module.exports={rank};
