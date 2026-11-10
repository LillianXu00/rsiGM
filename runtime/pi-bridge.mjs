// Trusted model boundary. Editable harnesses never receive credentials or this source.
import fs from 'node:fs';
import {createAgentSession, SessionManager, SettingsManager, DefaultResourceLoader, ModelRuntime} from '@earendil-works/pi-coding-agent';
import {AssistantMessageEventStream} from '@earendil-works/pi-ai';
const req=JSON.parse(fs.readFileSync(0,'utf8'));
if(!['mock','bigmodel'].includes(req.mode)) throw new Error('Unsupported provider');
const cwd=process.cwd();
const settingsManager=SettingsManager.inMemory({retry:{enabled:false},compaction:{enabled:false}});
const resourceLoader=new DefaultResourceLoader({cwd,agentDir:cwd,settingsManager,noExtensions:true,noSkills:true,noPromptTemplates:true,noThemes:true,systemPromptOverride:()=>req.system||'You are a coding agent.'});
await resourceLoader.reload();
const modelRuntime=await ModelRuntime.create({authPath:cwd+'/auth.json',modelsPath:null,refreshOnCreate:false});
if(req.mode==='mock') modelRuntime.hasConfiguredAuth=()=>true;
if(req.mode==='mock') modelRuntime.getAuth=async()=>({apiKey:'mock-not-secret'});
let model={id:'mock',name:'Mock',provider:'mock',api:'openai-completions',baseUrl:'http://invalid',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:32000,maxTokens:4096};
if(req.mode==='bigmodel'){
 modelRuntime.registerProvider('bigmodel',{baseUrl:req.base_url+'/v1',api:'openai-completions',apiKey:req.token,models:[{id:req.model,name:req.model,reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:200000,maxTokens:req.max_tokens,compat:{maxTokensField:'max_tokens',supportsDeveloperRole:false}}]});
 model=modelRuntime.getModel('bigmodel',req.model);
}
const {session}=await createAgentSession({cwd,agentDir:cwd,model,modelRuntime,resourceLoader,settingsManager,sessionManager:SessionManager.inMemory(),tools:[]});
if(req.mode==='mock') session.agent.streamFunction=()=>{
 const s=new AssistantMessageEventStream();
 const m={role:'assistant',content:[{type:'text',text:req.mock_response}],api:model.api,provider:'mock',model:'mock',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:Date.now()};
 queueMicrotask(()=>{s.push({type:'start',partial:m});s.push({type:'done',reason:'stop',message:m});s.end(m)});return s;
};
try{await session.prompt(req.prompt);const messages=session.messages.filter(m=>m.role==='assistant');const last=messages.at(-1);if(last?.stopReason==='error') throw new Error(last.errorMessage||'model error');console.log(JSON.stringify({text:session.getLastAssistantText(),stop_reason:last?.stopReason,content_types:last?.content?.map(c=>c.type),usage:req.mode==='mock'?{input:0,output:0,simulated:true}:last?.usage,runtime:'pi-sdk-1.5.1',model:model.id}));}finally{session.dispose()}
