'use strict';
const fs=require('node:fs');const path=require('node:path');
class Analytics {
  constructor(root){this.file=path.join(root,'lara','content','system-events.jsonl');this.counts={sessions:0,queries:0,languages:{},modes:{},requested_resources:{},channels:{text:0,voice:0},unanswered:0,provider_errors:0,total_latency_ms:0};}
  event(type,fields={}) { const record={time:new Date().toISOString(),type,...fields}; try{fs.appendFileSync(this.file,JSON.stringify(record)+'\n',{mode:0o600});}catch{} }
  query(language,mode,answered,resources=[],channel='text',latency=0){this.counts.queries++;this.counts.languages[language]=(this.counts.languages[language]||0)+1;this.counts.modes[mode]=(this.counts.modes[mode]||0)+1;this.counts.channels[channel]=(this.counts.channels[channel]||0)+1;if(!answered)this.counts.unanswered++;for(const title of resources)this.counts.requested_resources[title]=(this.counts.requested_resources[title]||0)+1;this.counts.total_latency_ms+=latency;this.event('query',{language,mode,answered,resource_count:resources.length,channel,latency_ms:latency});}
  snapshot(){return {...this.counts,average_response_ms:this.counts.queries?Math.round(this.counts.total_latency_ms/this.counts.queries):0,top_resources:Object.entries(this.counts.requested_resources).sort((a,b)=>b[1]-a[1]).slice(0,10)};}
}
module.exports={Analytics};
