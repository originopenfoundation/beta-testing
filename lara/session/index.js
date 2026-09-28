'use strict';
const crypto=require('node:crypto');
class Sessions {
  constructor(ttl=3600000){this.ttl=ttl;this.items=new Map();}
  get(id){const value=id&&this.items.get(id);if(!value||value.expires<Date.now()){if(id)this.items.delete(id);return null;} value.expires=Date.now()+this.ttl; return value;}
  create(){const id=crypto.randomBytes(32).toString('base64url');const data={messages:[],expires:Date.now()+this.ttl};this.items.set(id,data);return {id,data};}
  prune(){for(const [id,v] of this.items)if(v.expires<Date.now())this.items.delete(id);}
  clear(id){this.items.delete(id);}
}
module.exports={Sessions};
