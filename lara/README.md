# LaRA — OOF assistant layer

LaRA is a separately maintained, same-origin Node.js application and static-site widget. This repository is an English-only static OOF website (GitHub Pages workflows; no existing backend, database, authentication, or server-side routes were present). The included Node server serves the website and private, same-origin `/_lara/*` routes together. Deploy that server behind the OOF website's existing domain/reverse proxy to enable chat; GitHub Pages alone cannot run the backend. No canonical page is copied into LaRA or translated. The indexer reads root HTML and writes derived metadata and text chunks under `lara/content/`.

```text
OOF canonical HTML (read-only) -> indexing -> separate knowledge index
visitor -> widget -> language + intent -> retrieval -> methodology router/assessment
        -> response validation -> optional LLMProvider -> user's language + sources
```

`lara/server.js` composes the modular layers. Retrieval is deterministic and evidence-grounded; assessment reports user-provided facts, missing evidence, and potential gaps without declaring a system validated. The `AICommunicationGateway` dispatches to replaceable OpenRouter or OpenAI-compatible adapters; neither chooses resources nor determines methodology. With no key/provider, source-grounded localized responses remain available, and exact canonical-link requests bypass generation. Sessions are random, HTTP-only, same-site, short-lived and memory-only. Separate persistent stores hold redacted, provenance-backed candidate knowledge, experience and knowledge gaps; the canonical firewall prevents them from writing OOF pages. Recognition passphrases restore only non-sensitive continuity and are not authentication. The optional local admin requires `LARA_ADMIN_TOKEN`; provider keys never leave the server. Admin access is restricted to loopback in the MVP.

The widget is injected through the shared non-canonical `header.js` presentation shell. Voice uses browser speech interfaces behind `SpeechToTextProvider` / `TextToSpeechProvider` contracts; avatar/presentation adapters remain separate.

## Run

Requires Node.js 20 or later; no third-party runtime packages are needed.

1. `node lara/indexing/build-index.js` (or use the admin Re-index button).
2. Copy `.env.example` to `.env` and configure the desired provider. `LLM_PROVIDER` may be `none`, `openrouter`, or `openai-compatible`; set `LLM_MODEL`, `LLM_API_KEY`, and `LLM_BASE_URL` server-side as appropriate. Optional fallback uses `LLM_FALLBACK_PROVIDER`, `LLM_FALLBACK_MODEL`, `LLM_FALLBACK_API_KEY`, and `LLM_FALLBACK_BASE_URL`. No provider is required for the extractive MVP.
3. `node lara/server.js`; open `http://localhost:4173`.
4. For admin, set a long random `LARA_ADMIN_TOKEN`, then visit `http://localhost:4173/lara/admin/` and enter it. The token is held in session storage only and is never returned by the server.

The backend must run behind the OOF origin. Keep `/_lara/` same-origin, disable proxy caching for those paths, use HTTPS and set `NODE_ENV=production` so session cookies are secure, configure the proxy/body and request limits, and inject admin authentication at the trusted deployment boundary. Do not publish `.env`, the generated index, or admin pages as static public assets. This project contains no hosting credentials and does not change the existing GitHub Pages deployment.

## Configuration

See `.env.example`. `LLM_MODEL` is deliberately unset: select a currently available free OpenRouter model in server configuration. Provider errors fall back to the deterministic evidence-grounded response; optional configured provider fallback is supported. Provider adapters share the `generate`, `stream`, `healthCheck`, `getCapabilities`, `normalizeResponse`, and `normalizeError` contract. OpenAI-compatible integrations are only claimed for endpoints that honor the compatible chat-completions request. Voice uses supported browser APIs; speech-provider contracts can be replaced independently.

Add future communication languages through `lara/language/languages.json`: provide the display name, localized response labels, language-detection keywords, and canonical search-term aliases; add a script-detection pattern only when the writing system needs one. Restart the backend to load configuration. This does not create or modify translated OOF canonical pages.

## Canonical-content safeguard

The indexer reads source pages and writes only `lara/content/knowledge-index.json` and `lara/content/index-state.json`. It never writes to canonical HTML. Metadata fields that cannot be extracted directly are `null` or empty arrays; generated relationship suggestions are not canonical. Re-indexing compares source hashes to detect changed pages. Exclude any resource with the admin index toggle; this toggle changes only the separate runtime index.

## Governed learning and identity storage

Private server-side JSONL stores under `lara/content/learning/` hold `candidate-knowledge.jsonl`, `knowledge-gaps.jsonl`, and `experience.jsonl`. Records include a random learning ID, redacted observation, de-duplication key, timestamps, status, occurrence/usage counts, and interaction provenance. Session working memory remains ephemeral and distinct from these records. Repeated unsupported questions consolidate into gap observations. Model output alone is never stored as canonical or approved knowledge. Admin-only `/_lara/admin/learning` returns the export, and the review endpoint can change lifecycle status; review never edits canonical files. Protect and back up this private directory according to OOF retention policy.

Lightweight recognition data is stored separately in `lara/content/recognition-passphrases.json`; only the SHA-256 phrase hash, internal random identity ID, preferred name and non-sensitive continuity topics are stored. The passphrase is explicitly not authentication and cannot retrieve contact details or enquiries. Enquiries require a user-reviewed summary and an explicit confirmation; they are appended to private `lara/content/enquiries.jsonl`. The current implementation records enquiries for OOF follow-up but does not send email or notify an operator automatically. Secure, verified identity, retention automation and production administrator SSO/RBAC remain deployment work.

## Verification

Run `node --test tests/lara/*.test.js`. The upgrade tests cover learning de-duplication/provenance, canonical-file integrity, passphrase boundaries, provider replacement/failure, and credential non-disclosure.

## LaRA 2.0 implementation notes

- **Reused:** canonical index builder, index/rank retrieval, multilingual routing, evidence-limited methodology assessment, response validation, HTTP-only session memory, and local admin gate.
- **Added or upgraded:** profile-photo welcome UI and quick actions; opportunity discovery; controlled, explicitly confirmed enquiry recording; recognition passphrases; the `AICommunicationGateway`, OpenRouter and OpenAI-compatible adapters; persistent learning stores and admin inspection.
- **Storage/migration:** no database migration is required. Runtime JSONL/JSON records are created on demand under `lara/content/`; `.gitignore` and the static server keep them out of public assets. The ZIP excludes operational logs, runtime configuration, passphrases, enquiries and learning data. Back up and retention-manage these records at the deployment boundary.
- **Adapter contract:** `generate`, `stream`, `healthCheck`, `getCapabilities`, `normalizeResponse`, and `normalizeError`. Methodology, retrieval and validation remain independent of provider-specific request syntax.
- **Learning schema:** each item has a random `learning_id`, `type`, redacted `text`, `deduplication_key`, first source interaction ID/type, timestamps, canonical object references, confidence, validation status, usage count, occurrence count, provenance list and outcome signals. Candidate/gap/experience are separate JSONL stores. Review status changes do not promote knowledge into canonical OOF pages.
- **Enquiries:** consent-confirmed submissions are readable at the loopback/admin-protected `/_lara/admin/enquiries` endpoint. There is no email relay or outbound notification configured.
- **Deployment limits:** an OpenRouter model/key must be configured server-side before generative inference is active; without it the index-backed fallback still answers retrieval requests. A static GitHub Pages deployment cannot run this backend. Sessions are process-local and persistent JSON records target a single backend instance; production SSO/RBAC, shared storage, retention automation, monitoring and email notification require deployment integration.

## MVP scope and limitations

The static site has no existing server or admin identity system. The included backend is a deployment-ready starting point, not a claim that GitHub Pages can execute private code. The local admin's bearer token is a bootstrap gate, not a substitute for production OOF administrator SSO/RBAC. Browser speech support varies. Language detection is a dependency-free heuristic; an LLM can improve natural multilingual phrasing when configured. No vector database is introduced; title/metadata/keyword/chunk scoring and relationship expansion use the existing canonical pages and site graph.
