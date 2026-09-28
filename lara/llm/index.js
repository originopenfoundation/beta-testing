'use strict';
class ProviderError extends Error{constructor(kind,message,status){super(message);this.name='ProviderError';this.kind=kind;this.status=status;}}
class AIProviderAdapter{
 async generate(_input){throw new Error('AIProviderAdapter.generate must be implemented');}
 async stream(input,onDelta){const answer=await this.generate(input);if(onDelta)onDelta(answer);return answer;}
 async healthCheck(){return {status:'available',provider:this.name||'adapter'};}
 getCapabilities(){return {text:true,streaming:false,structured_output:false,tool_calling:false,multilingual:true,context_window:null};}
 normalizeResponse(json){const answer=json?.choices?.[0]?.message?.content?.trim();if(!answer)throw new ProviderError('provider_error','Provider returned an empty answer');return answer;}
 normalizeError(error){if(error instanceof ProviderError)return error;if(error?.name==='AbortError')return new ProviderError('timeout','Provider request timed out');const status=error?.status||Number(String(error.message).match(/returned (\d+)/)?.[1]);if(status===401||status===403)return new ProviderError('authentication_error','Provider authentication failed',status);if(status===429)return new ProviderError('rate_limited','Provider rate limit reached',status);if(status===404)return new ProviderError('model_unavailable','Configured model is unavailable',status);return new ProviderError('provider_error','Provider request failed',status||undefined);}
}
class OpenAICompatibleAdapter extends AIProviderAdapter{
 constructor(config){super();this.config=config;this.name=config.name||'openai-compatible';}
 async generate({question,language,mode,length,passages,assessment,signal}){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),this.config.timeout||20000);if(signal)signal.addEventListener('abort',()=>controller.abort(),{once:true});
  try{const response=await fetch(`${this.config.baseUrl.replace(/\/$/,'')}/chat/completions`,{method:'POST',signal:controller.signal,headers:{Authorization:`Bearer ${this.config.apiKey}`,'Content-Type':'application/json',...(this.config.headers||{})},body:JSON.stringify({model:this.config.model,temperature:0.15,max_tokens:this.config.maxTokens||700,messages:[{role:'system',content:`You are LaRA, the official OOF® AI Methodology Assistant. Answer in ${language}. Use only supplied canonical OOF evidence for OOF-specific claims. Do not invent definitions, relationships, standards, capability, prices, approvals or commitments. Identify limits when evidence is insufficient. Maintain a curious, precise, respectful and naturally conversational voice. Be light-hearted only when context is suitable. Keep personal/contact data private. ${mode==='methodology_application'?'Separate user-provided facts from canonical OOF evidence. Assessments are preliminary; never claim validation.':''} Output only user-facing prose. Response length: ${length}.`},{role:'user',content:JSON.stringify({question,canonical_sources:passages,assessment:assessment||null})}]})});if(!response.ok)throw Object.assign(new Error(`Provider returned ${response.status}`),{status:response.status});return this.normalizeResponse(await response.json());}
  catch(error){throw this.normalizeError(error);}finally{clearTimeout(timeout);}
 }
 getCapabilities(){return {text:true,streaming:false,structured_output:false,tool_calling:false,multilingual:true,context_window:null};}
}
class OpenRouterAdapter extends OpenAICompatibleAdapter{constructor(config){super({...config,name:'openrouter'});}}
class AICommunicationGateway{
 constructor({primary=null,fallback=null}={}){this.primary=primary;this.fallback=fallback;}
 getCapabilities(){return this.primary?.getCapabilities()||{text:false,streaming:false,structured_output:false,tool_calling:false,multilingual:true,context_window:null};}
 async healthCheck(){if(!this.primary)return {status:'unavailable',provider:'none'};return this.primary.healthCheck();}
 async generate(input){if(!this.primary)return null;try{return await this.primary.generate(input);}catch(error){if(this.fallback)try{return await this.fallback.generate(input);}catch(fallbackError){throw this.primary.normalizeError?.(fallbackError)||fallbackError;}throw this.primary.normalizeError?.(error)||error;}}
}
function adapterFrom(env,prefix='LLM_'){
 const provider=env[`${prefix}PROVIDER`]||'none',model=env[`${prefix}MODEL`],apiKey=env[`${prefix}API_KEY`];if(!apiKey||!model||provider==='none')return null;
 const config={apiKey,model,baseUrl:env[`${prefix}BASE_URL`]||(provider==='openrouter'?'https://openrouter.ai/api/v1':'https://api.openai.com/v1'),timeout:Math.min(Number(env[`${prefix}TIMEOUT`])||20000,60000),maxTokens:Math.min(Number(env[`${prefix}MAX_TOKENS`])||700,2000),headers:provider==='openrouter'?{'HTTP-Referer':env.LARA_SITE_URL||'https://originopenfoundation.org','X-Title':'OOF LaRA'}:{}};
 if(provider==='openrouter')return new OpenRouterAdapter(config);if(provider==='openai-compatible')return new OpenAICompatibleAdapter(config);return null;
}
function createGateway(env){const primary=adapterFrom(env);const fallback=env.LLM_FALLBACK_PROVIDER&&env.LLM_FALLBACK_PROVIDER!=='none'?adapterFrom({...env,LLM_PROVIDER:env.LLM_FALLBACK_PROVIDER,LLM_MODEL:env.LLM_FALLBACK_MODEL||env.LLM_MODEL,LLM_API_KEY:env.LLM_FALLBACK_API_KEY||env.LLM_API_KEY,LLM_BASE_URL:env.LLM_FALLBACK_BASE_URL||env.LLM_BASE_URL},'LLM_'):null;return new AICommunicationGateway({primary,fallback});}
function createProvider(env){return createGateway(env).primary;}
module.exports={ProviderError,AIProviderAdapter,OpenAICompatibleAdapter,OpenRouterAdapter,OpenRouterProvider:OpenRouterAdapter,AICommunicationGateway,createGateway,createProvider};
