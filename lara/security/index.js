'use strict';
const crypto=require('node:crypto');
function safeEqual(a,b){const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));return x.length===y.length&&crypto.timingSafeEqual(x,y);}
function rateLimiter(limit=20,windowMs=60000){const hits=new Map();return ip=>{const now=Date.now();const item=hits.get(ip)||{start:now,count:0};if(now-item.start>windowMs){item.start=now;item.count=0;}item.count++;hits.set(ip,item);return item.count<=limit;};}
module.exports={safeEqual,rateLimiter};
