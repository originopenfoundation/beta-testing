'use strict';
const fs=require('node:fs');const path=require('node:path');
const config=JSON.parse(fs.readFileSync(path.join(__dirname,'languages.json'),'utf8'));
const LANGUAGES=Object.fromEntries(Object.entries(config.languages||{}).map(([id,value])=>[id,{...value}]));
const lexicon=Object.fromEntries(Object.entries(LANGUAGES).map(([id,value])=>[id,value.detection_keywords||[]]));
const aliases=Object.fromEntries(Object.entries(LANGUAGES).map(([id,value])=>[id,value.term_aliases||{}]));
function normalize(word){return String(word).toLocaleLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'');}
const stopWords=new Set((config.stop_words||[]).map(normalize));
const scripts=(config.script_detection||[]).map(x=>[x.language,new RegExp(x.pattern,'u')]);
function detect(text,preferred='auto'){
  if(preferred&&preferred!=='auto'&&LANGUAGES[preferred])return preferred;
  for(const [lang,re] of scripts)if(re.test(text))return lang;
  const lowered=String(text).toLocaleLowerCase();let best=Object.keys(LANGUAGES)[0]||'en',score=0;
  for(const [lang,words] of Object.entries(lexicon)){const n=words.reduce((sum,w)=>sum+(lowered.includes(w)?1:0),0);if(n>score){best=lang;score=n;}}
  return best;
}
function queryTerms(text,lang){
  const original=String(text);const lowered=original.toLocaleLowerCase();
  const names=[...original.matchAll(/\b[A-Z][A-Z0-9]{1,9}\b/g)].map(m=>m[0]);
  const words=lowered.match(/[\p{L}\p{N}™®-]{2,}/gu)||[];const knownAliases=aliases[lang]||{};
  const normalized=words.map(normalize).filter(w=>!stopWords.has(w));
  for(const [from,to] of Object.entries(knownAliases))if(lowered.includes(from.toLocaleLowerCase())&&!stopWords.has(normalize(to)))normalized.push(to);
  return [...new Set([...names,...normalized])];
}
module.exports={LANGUAGES,lexicon,aliases,config,detect,queryTerms};
