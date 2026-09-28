'use strict';
const fs=require('node:fs');const path=require('node:path');const crypto=require('node:crypto');
const words=['Amber','Birch','Blue','Cedar','Clear','Copper','Cobalt','Dawn','Delta','Ember','Fern','Harbor','Indigo','Juniper','Lumen','Maple','Mosaic','North','Olive','Orbit','River','Silver','Summit','Willow'];
class RecognitionStore{
 constructor(root){this.file=path.join(root,'lara','content','recognition-passphrases.json');}
 read(){try{return JSON.parse(fs.readFileSync(this.file,'utf8'));}catch{return {identities:[]};}}
 write(data){fs.mkdirSync(path.dirname(this.file),{recursive:true});const temp=this.file+'.tmp';fs.writeFileSync(temp,JSON.stringify(data,null,2),{mode:0o600});fs.renameSync(temp,this.file);}
 create(preferredName,topics=[]){const name=String(preferredName||'').trim().slice(0,60);if(!name)throw new Error('Preferred name is required');const data=this.read();let phrase,id;do{phrase=`${name} — ${words[crypto.randomInt(words.length)]} ${words[crypto.randomInt(words.length)]}`;id=crypto.randomUUID();}while(data.identities.some(x=>x.phrase_hash===this.hash(phrase)));data.identities.push({identity_id:id,phrase_hash:this.hash(phrase),preferred_name:name,created_at:new Date().toISOString(),updated_at:new Date().toISOString(),non_sensitive_memory:{methodology_topics:[...new Set(topics.filter(x=>typeof x==='string').map(x=>x.slice(0,100)))].slice(-12)}});this.write(data);return {identity_id:id,recognition_passphrase:phrase,security_notice:'This phrase is not authentication and cannot restore enquiries, contact information or restricted content.'};}
 restore(phrase){const data=this.read(),record=data.identities.find(x=>x.phrase_hash===this.hash(String(phrase||'').trim()));if(!record)return null;record.updated_at=new Date().toISOString();this.write(data);return {preferred_name:record.preferred_name,non_sensitive_memory:record.non_sensitive_memory};}
 hash(phrase){return crypto.createHash('sha256').update(phrase.toLocaleLowerCase()).digest('hex');}
}
module.exports={RecognitionStore};
