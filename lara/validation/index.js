'use strict';
function validate(answer, question, sources) {
  if(typeof answer!=='string'||!answer.trim()||answer.length>20000)return {ok:false,reason:'empty_or_oversized'};
  const trusted=(String(question)+' '+sources.map(s=>`${s.title} ${s.text}`).join(' '));
  const acronyms=[...answer.matchAll(/\b[A-Z][A-Z0-9]{2,10}\b/g)].map(m=>m[0]);
  if(acronyms.some(word=>!new RegExp(`\\b${word}\\b`,'i').test(trusted)))return {ok:false,reason:'unsupported_acronym'};
  const numbers=[...answer.matchAll(/\b\d+(?:[.,]\d+)?\b/g)].map(m=>m[0]);
  if(numbers.some(n=>!trusted.includes(n)))return {ok:false,reason:'unsupported_number'};
  return {ok:true};
}
module.exports={validate};
