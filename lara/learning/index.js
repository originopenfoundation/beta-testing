'use strict';
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const secretPatterns=[/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi,/(?<!\w)\+?\d[\d ()-]{7,}\d(?!\w)/g,/(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,})/g,/(?:password|passwd|secret|api[_ -]?key)\s*[:=]\s*[^\s,;]+/gi];
function sanitize(value){let text=String(value||'');for(const re of secretPatterns)text=text.replace(re,'[redacted]');text=text.replace(/\b(?:my name is|i am|i'm|this is|name:)\s+[\p{L}][\p{L}' -]{1,60}/giu,'[name redacted]');return text.replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim().slice(0,800);}
function keyFor(type,text){return crypto.createHash('sha256').update(`${type}\n${sanitize(text).toLocaleLowerCase()}`).digest('hex');}
function similarity(a,b){const words=x=>new Set(sanitize(x).toLocaleLowerCase().match(/[\p{L}\p{N}]{3,}/gu)||[]),left=words(a),right=words(b);if(!left.size||!right.size)return 0;let common=0;for(const word of left)if(right.has(word))common++;return common/(left.size+right.size-common);}
class LearningLibrary{
 constructor(root){this.dir=path.join(root,'lara','content','learning');this.files={candidate:path.join(this.dir,'candidate-knowledge.jsonl'),gap:path.join(this.dir,'knowledge-gaps.jsonl'),experience:path.join(this.dir,'experience.jsonl')};fs.mkdirSync(this.dir,{recursive:true});}
 read(type){try{return fs.readFileSync(this.files[type],'utf8').split(/\r?\n/).filter(Boolean).map(x=>JSON.parse(x));}catch{return [];}}
 record(type,text,{interactionId,sourceType='visitor_interaction',objects=[],confidence=0.35,status='candidate',outcome}={}){
  if(!this.files[type]||!interactionId)throw new Error('Persistent learning requires a valid type and provenance interactionId');
  const safe=sanitize(text);if(safe.length<8)return null;const key=keyFor(type,safe),records=this.read(type),prior=records.find(r=>r.deduplication_key===key)||(type==='gap'?records.find(r=>similarity(r.text,safe)>=0.72):null);
  if(prior){prior.occurrences++;prior.updated_at=new Date().toISOString();prior.provenance.push({interaction_id:interactionId,source_type:sourceType,created_at:prior.updated_at});if(outcome)prior.outcomes.push(sanitize(outcome));this.write(type,records);return prior;}
  const now=new Date().toISOString(),record={learning_id:crypto.randomUUID(),type,text:safe,deduplication_key:key,source_interaction_id:interactionId,source_type:sourceType,created_at:now,updated_at:now,relevant_oof_objects:objects.filter(x=>typeof x==='string').slice(0,10),confidence:Math.max(0,Math.min(1,Number(confidence)||0)),validation_status:status,usage_count:0,occurrences:1,provenance:[{interaction_id:interactionId,source_type:sourceType,created_at:now}],outcomes:outcome?[sanitize(outcome)]:[]};records.push(record);this.write(type,records);return record;
 }
 write(type,records){const target=this.files[type],temp=target+'.tmp';fs.writeFileSync(temp,records.map(x=>JSON.stringify(x)).join('\n')+(records.length?'\n':''),{mode:0o600});fs.renameSync(temp,target);}
 observeGap(question,interactionId){return this.record('gap',question,{interactionId,sourceType:'repeated_unsupported_question',confidence:0.4,status:'observed'});}
 export(){return Object.fromEntries(Object.keys(this.files).map(k=>[k,this.read(k)]));}
}
module.exports={LearningLibrary,sanitize,keyFor,similarity};
