#!/usr/bin/env node
'use strict';
// Read-only crawler for canonical root HTML. All output is in the LaRA data layer.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const root = path.resolve(process.env.LARA_SITE_ROOT||path.resolve(__dirname, '../..'));
const output = path.resolve(process.env.LARA_INDEX_OUTPUT_DIR||path.resolve(__dirname, '../content'));
const baseUrl = process.env.OOF_CANONICAL_BASE_URL || 'https://originopenfoundation.org/';
const entityMap = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ', '#39': "'" };
function decodeEntities(s) {
  return s.replace(/&(#x[\da-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === '#') { const n = e[1].toLowerCase() === 'x' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10); return Number.isFinite(n) ? String.fromCodePoint(n) : m; }
    return entityMap[e.toLowerCase()] ?? m;
  });
}
function textOf(html) {
  return decodeEntities(html.replace(/<!--[\s\S]*?-->/g, ' ').replace(/<(script|style|noscript|svg|nav|footer)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, ' ')
    .replace(/<\/(p|div|section|article|li|h[1-6]|br|tr|main)>/gi, '\n').replace(/<[^>]+>/g, ' '))
    .replace(/[\t\f\r ]+/g, ' ').replace(/ *\n */g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}
function match(html, re) { return html.match(re)?.[1] || null; }
function metadata(file, html) {
  const title = decodeEntities(match(html, /<title[^>]*>([\s\S]*?)<\/title>/i) || match(html, /<h1\b[^>]*>([\s\S]*?)<\/h1>/i) || path.basename(file, '.html')).replace(/<[^>]+>/g, '').trim();
  const canonical = match(html, /<link\b[^>]*rel=["']canonical["'][^>]*href=["']([^"']+)/i) || match(html, /<link\b[^>]*href=["']([^"']+)["'][^>]*rel=["']canonical["']/i);
  const identity=title+' '+path.basename(file,'.html');
  const type = /\babout\b.*\barchitecture\b/i.test(identity) ? 'About Architecture' : /\babout\b.*\bstandard\b/i.test(identity) ? 'About Standard' : /architecture map/i.test(identity) ? 'Architecture Map' : /complete .*index|standards? index/i.test(identity) ? 'Architecture Index' : /architecture/i.test(identity) ? 'Architecture' : /\bstandard\b/i.test(identity) ? 'Parent Standard' : /\bmodule\b/i.test(identity) ? 'Core Module' : 'Methodology Resource';
  const headings = [...html.matchAll(/<h[1-3]\b[^>]*>([\s\S]*?)<\/h[1-3]>/gi)].map(m => textOf(m[1])).filter(Boolean).slice(0, 80);
  const acronym = title.match(/\(([A-Z][A-Z0-9™®-]{1,14})\)/)?.[1] || title.match(/\b([A-Z][A-Z0-9]{2,9})\b/)?.[1] || null;
  const relPath = path.relative(root, file).replaceAll(path.sep, '/');
  const url = canonical || new URL(encodeURI(relPath), baseUrl).href;
  const id = relPath.replace(/\.html$/i, '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-|-$/g, '');
  const topics = headings.slice(0, 12);
  const keywords = [...new Set([...(acronym ? [acronym] : []), ...title.split(/[^\p{L}\p{N}™®]+/u).filter(w => w.length > 3).slice(0, 20)])];
  return { resource_id: id || 'home', title, resource_type: type, architecture: null,
    parent_standard: type === 'Parent Standard' || type==='About Standard' ? title : null, module: type === 'Core Module' ? title : null,
    category: null, subcategory: null, governed_space: null, canonical_language: 'English', canonical_url: url,
    topics, keywords, questions_addressed: [], related_resources: [], version: null, status: null, source_path: relPath,
    source_hash: crypto.createHash('sha256').update(html).digest('hex'), chunks: [] };
}
function chunks(text, maxChars = 1500, overlap = 180) {
  const paragraphs = text.split(/\n+/).map(s => s.trim()).filter(Boolean); const out = []; let current = '';
  for (const para of paragraphs) {
    if (para.length > maxChars) {
      if (current) { out.push(current); current = ''; }
      for (let i = 0; i < para.length; i += maxChars - overlap) out.push(para.slice(i, i + maxChars));
    } else if (current && current.length + para.length > maxChars) { out.push(current); current = para; }
    else current += (current ? '\n' : '') + para;
  }
  if (current) out.push(current);
  return out;
}
function walk(dir) { return fs.readdirSync(dir, { withFileTypes: true }).flatMap(e => e.isDirectory() ? (['.git', 'node_modules', 'lara'].includes(e.name) ? [] : walk(path.join(dir, e.name))) : e.isFile() && e.name.toLowerCase().endsWith('.html') ? [path.join(dir, e.name)] : []); }
fs.mkdirSync(output, { recursive: true });
const priorPath = path.join(output, 'index-state.json');
const prior = fs.existsSync(priorPath) ? JSON.parse(fs.readFileSync(priorPath, 'utf8')) : { pages: {} };
const resources = [];
const pages = {};
for (const file of walk(root)) {
  const html = fs.readFileSync(file, 'utf8'); const resource = metadata(file, html); const body = textOf(html);
  resource.chunks = chunks(body).map((text, i) => ({ chunk_id: `${resource.resource_id}:${i + 1}`, text }));
  resources.push(resource); pages[resource.source_path] = resource.source_hash;
}
resources.sort((a, b) => a.canonical_url.localeCompare(b.canonical_url));
// Reuse OOF's own approved structured registries for resource associations.
const byUrl = new Map(resources.map(r => [r.canonical_url.replace(/\/$/, ''), r]));
const byPath = new Map(resources.map(r => [r.source_path.replaceAll('\\', '/').toLowerCase(), r]));
const registryPath=path.join(root,'data/oof-architecture-registry.json');
if(fs.existsSync(registryPath)) {
  const registry=JSON.parse(fs.readFileSync(registryPath,'utf8'));
  for(const arch of registry.architectures||[]) {
    for(const r of resources) if((r.title+' '+r.source_path).toLocaleLowerCase().includes(String(arch.acronym||'').toLocaleLowerCase()) && /architecture/i.test(r.title+' '+r.source_path)) {r.architecture=arch.acronymLabel||arch.acronym||arch.displayName;if(['Architecture','Architecture Map','Architecture Index','About Architecture'].includes(r.resource_type))r.status=arch.status||null;}
    const paths=[...(arch.resources||[]),...(arch.standards||[]).flatMap(s=>[s,...(s.modules||[])])].map(x=>x.url).filter(Boolean);
    for(const rel of paths) { const r=byPath.get(rel.replaceAll('\\','/').toLowerCase()); if(r){r.architecture=arch.acronymLabel||arch.acronym||arch.displayName; const entry=[...(arch.resources||[]),...(arch.standards||[]).flatMap(s=>[s,...(s.modules||[])])].find(x=>x.url===rel);if(entry?.id)r.parent_standard=entry.id;else if(entry?.name&&entry.name.toLowerCase().includes('standard'))r.parent_standard=entry.name;} }
    for(const s of arch.standards||[]) {
      for(const rel of [s.url,s.about?.url,...(s.modules||[]).map(m=>m.url)].filter(Boolean)){const r=byPath.get(rel.replaceAll('\\','/').toLowerCase());if(r){r.architecture=arch.acronymLabel||arch.acronym||arch.displayName;r.parent_standard=s.id||s.name||null;if((s.modules||[]).some(m=>m.url===rel)){r.resource_type='Core Module';r.module=(s.modules||[]).find(m=>m.url===rel)?.title||r.title;}}}
    }
  }
}
const versionPath=path.join(root,'data/oof-version-registry.json');
if(fs.existsSync(versionPath)) {
  const versions=JSON.parse(fs.readFileSync(versionPath,'utf8'));
  for(const v of versions.resources||[]){const r=byUrl.get(String(v.canonicalUrl||'').replace(/\/$/,''))||byPath.get(String(v.resourcePath||'').replaceAll('\\','/').toLowerCase());if(r){r.version=v.version||null;r.status=v.status||null;}}
}
const relationshipsPath=path.join(root,'data/oof-typed-relationships.json');
if(fs.existsSync(relationshipsPath)) {
  const graph=JSON.parse(fs.readFileSync(relationshipsPath,'utf8')); const ids=new Map(resources.map(r=>[r.canonical_url.replace(/\/$/,''),r.resource_id]));
  for(const rel of graph.relationships||[]) { const source=ids.get(String(rel.source||'').replace(/\/$/,'')); const target=ids.get(String(rel.target||'').replace(/\/$/,'')); if(source&&target&&source!==target) {const r=resources.find(x=>x.resource_id===source); if(r)r.related_resources.push({resource_id:target,relationship:rel.type||null});} }
}
const changed = Object.keys(pages).filter(p => prior.pages?.[p] !== pages[p]);
const removed = Object.keys(prior.pages || {}).filter(p => !(p in pages));
const indexedAt = new Date().toISOString();
const index = { schema_version: 1, canonical_language: 'English', generated_at: indexedAt, resource_count: resources.length, resources };
const tmp = path.join(output, 'knowledge-index.json.tmp'); fs.writeFileSync(tmp, JSON.stringify(index)); fs.renameSync(tmp, path.join(output, 'knowledge-index.json'));
fs.writeFileSync(path.join(output, 'index-state.json'), JSON.stringify({ generated_at: indexedAt, resource_count: resources.length, changed_pages: changed, removed_pages: removed, pages }, null, 2));
if(fs.existsSync(registryPath)) {
  const registry=JSON.parse(fs.readFileSync(registryPath,'utf8'));
  const descriptors=(registry.architectures||[]).map(a=>({architecture_id:a.acronym||null,canonical_name:a.displayName||null,canonical_language:'English',source_registry:'data/oof-architecture-registry.json',source_status:a.status||null,resource_urls:[...(a.resources||[]),...(a.standards||[])].map(r=>new URL(encodeURI(r.url),baseUrl).href),governed_spaces:[],methodology_questions:[],routing_terms:[a.acronym,a.acronymLabel,a.displayName].filter(Boolean)}));
  fs.writeFileSync(path.join(output,'methodology-descriptors.json'),JSON.stringify({schema_version:1,generated_at:indexedAt,notice:'Machine routing metadata references the OOF architecture registry; it is not canonical methodology.',architectures:descriptors},null,2));
}
console.log(`Indexed ${resources.length} canonical HTML resources; ${changed.length} changed, ${removed.length} removed.`);
