# AUREN — Phase 3C Vercel Source Investigation

**Inspection Date:** 2026-11-17  
**Mode:** STRICTLY READ-ONLY — Investigation Only  
**Investigator:** Antigravity Agent

---

## Executive Summary

The AUREN Vercel deployment at `https://frontend-alpha-steel-64.vercel.app` is displaying a **Phase 3A** single-page application because GitHub (`origin/main`) contains only the Phase 3A frontend codebase. The entire Phase 3C frontend implementation (13 commits, 65 changed frontend files, all new routes, Memory Explorer, Tasks, Projects, Goals, Omnisearch, Reflection, etc.) exists **exclusively in the local `/home/kali/AUREN` workspace** and has never been pushed to GitHub.

Vercel reads from GitHub. GitHub has Phase 3A. Therefore Vercel deploys Phase 3A.

This is the single root cause of the visual mismatch.

The backend connection failure (`NetworkError when attempting to fetch resource`) is a separate, independent issue: the production Vercel build has no `VITE_API_BASE_URL` environment variable set, so the app falls back to `http://localhost:8000/api/v1` which does not exist on the internet.

---

## Comparison Table

| Item | Local Workspace | GitHub (`origin/main`) | Vercel Deployment |
|---|---|---|---|
| Repository | `solomon476/AUREN-Personal-AI` | `solomon476/AUREN-Personal-AI` | Reads from GitHub |
| Branch | `main` | `main` | `main` |
| Commit SHA | `96c8488e63b2d4ed2d037ebf03f51b077a1d03fb` | `9babc6d0f3a6a623f962560b1929cb42cb2908ff` | `9babc6d` (triggered build) |
| Commits ahead of GitHub | **13 commits ahead** | Base (not updated) | — |
| Frontend directory | `frontend/` | `frontend/` | Root dir: `frontend/` |
| App architecture | TanStack Router, 13 routes, multi-view SPA | Single-file `App.tsx`, no router | Phase 3A single-view |
| Application version | Phase 3C | Phase 3A | Phase 3A |
| Phase 3C features | ✅ All 11 views implemented | ❌ None present | ❌ Not deployed |
| Backend configuration | `VITE_API_BASE_URL` env var (fallback: localhost) | `VITE_API_BASE_URL` env var (fallback: localhost) | ❌ Falls back to localhost:8000 |
| Bundle filename | `index-Bizfs9nD.js` | Built from Phase 3A App.tsx → `index-CvzRr8NJ.js` | `index-CvzRr8NJ.js` |

---

## 1. Local Repository Findings

### Git State

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD commit | `96c8488e63b2d4ed2d037ebf03f51b077a1d03fb` |
| Working tree | Clean (3 untracked doc files; not in push scope) |
| Remote URL | `git@github.com:solomon476/AUREN-Personal-AI.git` |
| Commits ahead of origin | **13** |
| Commits behind origin | **0** |
| Expected commit present? | ✅ Yes — `96c8488` = HEAD |

### Local Phase 3C Frontend Architecture

The local `frontend/src/` contains the complete Phase 3C implementation:

```
frontend/src/
├── App.tsx                    (23 lines — thin RouterProvider wrapper)
├── router.tsx                 (13 routes registered via TanStack Router)
├── features/
│   ├── chat/ChatView.tsx
│   ├── memory/MemoryView.tsx
│   ├── tasks/TasksView.tsx
│   ├── projects/ProjectsView.tsx
│   ├── goals/GoalsView.tsx
│   ├── productivity/ProductivityDashboardView.tsx
│   ├── search/OmnisearchView.tsx
│   ├── reflection/ReflectionView.tsx
│   └── system/SystemView.tsx
├── components/
│   ├── auth/AuthModal.tsx, UserProfileMenu.tsx
│   ├── chat/ContextInspectorModal.tsx, MessageContent.tsx, ...
│   ├── layout/AppLayout.tsx, NavigationSidebar.tsx
│   ├── memory/MemoryDetailModal.tsx
│   ├── placeholders/SectionPlaceholder.tsx
│   └── productivity/TaskModal.tsx, ProjectModal.tsx, GoalModal.tsx
├── api/
│   ├── client.ts, chat.ts, auth.ts, memories.ts, productivity.ts, search.ts
├── hooks/
│   ├── useProductivity.ts, useSearch.ts
└── test/  (11 Vitest unit test files)
```

### Local Phase 3C Commit History (13 commits not on GitHub)

| SHA | Timestamp | Message |
|---|---|---|
| `96c8488` | 2026-11-17 18:45 +03 | feat(integration): Phase 3C master completion, brand alignment |
| `be1f4cf` | 2026-11-17 18:35 +03 | fix(search): Phase 3C.5.2 Security & Reflection Corrections |
| `c0e7a6c` | 2026-11-17 07:31 +03 | feat(search): Phase 3C.5 Reflective Intelligence & Omnisearch |
| `b8541c1` | 2026-11-17 00:25 +03 | fix(productivity): Phase 3C.4.1 ownership integrity |
| `014e889` | 2026-11-16 22:11 +03 | feat(productivity): Phase 3C.4 Productivity Core |
| `dc66f3e` | 2026-11-16 21:15 +03 | fix(memory): Phase 3C.3 corrective milestone |
| `faef9a8` | 2026-11-16 19:23 +03 | feat(memory): Phase 3C.3 memory management |
| `5c04e98` | 2026-11-16 17:50 +03 | feat(chat): Phase 3C.2 conversational hardening |
| `a63d7c6` | 2026-11-16 16:55 +03 | feat(frontend): Phase 3C.1 routing & layout foundation |
| `c6c53a7` | 2026-11-16 16:38 +03 | fix(memory): Phase 3B.2.2 worker shutdown |
| `1183131` | 2026-11-16 16:12 +03 | fix(memory): Phase 3B.2.2 retrieval identity |
| `f21e913` | 2026-11-16 15:49 +03 | fix(memory): Phase 3B.2.2 embedding model migration |
| `d7bbbce` | 2026-11-16 15:21 +03 | feat(memory): Phase 3B.2.2 persistent memory pipeline |

---

## 2. GitHub Findings

### GitHub `origin/main` State

| Item | Value |
|---|---|
| Latest commit | `9babc6d0f3a6a623f962560b1929cb42cb2908ff` |
| Commit timestamp | 2026-11-16 14:26:55 +0300 |
| Commit message | `fix(memory): correct hybrid retrieval weights and enforce epistemic status labeling in context injection` |
| Phase 3C commits present? | **❌ No — zero Phase 3C commits exist on GitHub** |
| Phase 3A frontend present? | ✅ Yes — full Phase 3A single-page app |

### GitHub Frontend Source (`origin/main:frontend/src/`)

```
frontend/src/
├── App.tsx       (347 lines — monolithic Phase 3A dashboard + health check + chat)
├── api/
│   ├── auth.ts
│   ├── chat.ts
│   ├── client.ts  (localhost:8000 fallback, same pattern)
│   ├── health.ts
│   └── types.ts
├── components/
│   └── auth/   (AuthModal.tsx, UserProfileMenu.tsx only)
├── context/
├── features/
│   └── chat/   (ChatView.tsx only — no other feature views)
├── lib/
├── index.css
├── main.tsx
└── vite-env.d.ts
```

**Key observation:** GitHub `frontend/src/features/` contains only `chat/`. No `memory/`, `tasks/`, `projects/`, `goals/`, `productivity/`, `search/`, `reflection/`, or `system/` directories. GitHub has no `router.tsx` at all.

### Phase Identification of GitHub Frontend

The GitHub `App.tsx` contains these literal strings, confirmed by source inspection:

```
"Phase 3A"
"Phase 3A: Persistent Chat & SSE Streaming"
"AUREN Personal AI Assistant • Phase 3A Persistent Chat & Streaming"
```

This is definitively a Phase 3A codebase, not Phase 3C.

---

## 3. Vercel Project Configuration

### Deployment Evidence from HTTP Headers

```
last-modified: Mon, 16 Nov 2026 21:04:48 GMT
x-vercel-cache: HIT
etag: "baa22038df426471440cce5d0940c323"
```

The deployed HTML references bundle: `/assets/index-CvzRr8NJ.js`

The local Phase 3C build produces: `/assets/index-Bizfs9nD.js`

**These are different bundles — the deployed bundle is built from GitHub Phase 3A source.**

### Deployment Timestamp Analysis

- GitHub `origin/main` latest commit timestamp: `2026-11-16 14:26:55 +0300` = `11:26:55 UTC`
- Vercel `last-modified` for deployed HTML: `2026-11-16 21:04:48 GMT`
- The deployment build time (21:04 UTC) is after the commit time (11:26 UTC), consistent with Vercel building commit `9babc6d` shortly after it was pushed to GitHub.

### Deployed Bundle Phase Evidence

```bash
$ grep 'Phase 3' deployed_bundle
"Phase 3A"
"Phase 3A: Persistent Chat & SSE Streaming"
"Phase 3A Persistent Chat & Streaming"
```

**Confirmed: Vercel is serving a bundle built from the Phase 3A GitHub source (`9babc6d`).**

### Backend URL in Deployed Bundle

```bash
$ grep 'localhost' deployed_bundle
localhost:8000  (appears twice — the fallback baked in by Vite)
```

No production backend URL found. `VITE_API_BASE_URL` was not set during the Vercel build, so Vite baked in the localhost:8000 fallback string into the production bundle.

---

## 4. Frontend Architecture Comparison

### Feature Presence Comparison

| Feature | Local (Phase 3C) | GitHub (Phase 3A) | Vercel Deployed |
|---|---|---|---|
| Authentication modal | ✅ Full | ✅ Basic | ✅ Basic (Phase 3A) |
| App layout + sidebar nav | ✅ Full 13-route nav | ❌ No sidebar | ❌ No sidebar |
| Chat interface | ✅ Streaming, SSE, history | ✅ Basic SSE chat | ✅ Basic SSE (Phase 3A) |
| Conversation history | ✅ Full | ❌ Not present | ❌ Not deployed |
| Memory Explorer | ✅ Full | ❌ Not present | ❌ Not deployed |
| Memory detail & lineage | ✅ Full | ❌ Not present | ❌ Not deployed |
| Context Inspector | ✅ Full | ❌ Not present | ❌ Not deployed |
| Tasks & Timetable | ✅ Full | ❌ Not present | ❌ Not deployed |
| Projects Workspace | ✅ Full | ❌ Not present | ❌ Not deployed |
| Strategic Goals | ✅ Full | ❌ Not present | ❌ Not deployed |
| Productivity Dashboard | ✅ Full | ❌ Not present | ❌ Not deployed |
| Omnisearch | ✅ Full | ❌ Not present | ❌ Not deployed |
| Reflection Dashboard | ✅ Full | ❌ Not present | ❌ Not deployed |
| Contradiction findings | ✅ Full | ❌ Not present | ❌ Not deployed |
| Staleness findings | ✅ Full | ❌ Not present | ❌ Not deployed |
| Settings | ✅ Placeholder | ❌ Not present | ❌ Not deployed |
| System telemetry | ✅ Full | ✅ Full (Phase 3A style) | ✅ Deployed (Phase 3A style) |
| Phase 3C routes | ✅ 13 routes | ❌ 0 (single-page) | ❌ No routing |

---

## 5. Backend Connectivity Findings

### Root Cause: `localhost:8000` baked into production bundle

The API client in both Phase 3A (GitHub) and Phase 3C (local) use:

```typescript
const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
```

Vite replaces `import.meta.env.VITE_API_BASE_URL` at build time. If `VITE_API_BASE_URL` is not defined in the Vercel environment, the entire expression evaluates to `'http://localhost:8000/api/v1'` and that string is baked into the production bundle.

**Evidence:** The deployed bundle `index-CvzRr8NJ.js` was confirmed to contain `localhost:8000` twice (the URL string itself, appearing in both the main client and chat module).

### Backend Availability

The backend is a FastAPI application that runs locally. No evidence of a publicly deployed backend URL exists in any source file, environment example, or documentation. The backend has not been deployed to any hosting provider — it is local-only.

### Classification of Errors

| Error Type | Applies? | Evidence |
|---|---|---|
| Missing `VITE_API_BASE_URL` env var | **✅ Confirmed** | localhost:8000 appears in bundle |
| Backend not deployed | **✅ Confirmed** | No production URL found anywhere |
| CORS configuration issue | Cannot determine | Backend unreachable before CORS check |
| API contract mismatch | Not applicable | Backend not reachable at all |
| DNS failure | Not applicable | localhost:8000 is not a DNS-resolvable host |

---

## 6. Root Cause Analysis

### Finding 1 — Phase 3C frontend was never pushed to GitHub
**Confidence: Certain (proven by Git log)**

- **Evidence:** `git log origin/main..HEAD` shows 13 commits. `git show origin/main:frontend/src/features/` shows only `chat/`. The Phase 3A `App.tsx` contains 347 lines and explicit "Phase 3A" branding.
- **Root cause:** Developers never executed `git push origin main` after completing any Phase 3C commit.
- **Impact:** Vercel has never received the Phase 3C source.

### Finding 2 — Vercel is correctly configured but deploying the wrong (outdated) source
**Confidence: High (confirmed by bundle content and timestamp)**

- **Evidence:** Vercel deployed bundle `index-CvzRr8NJ.js` contains "Phase 3A" strings. `last-modified` header matches a build triggered shortly after `9babc6d` was pushed. Bundle hash differs from local Phase 3C build (`index-Bizfs9nD.js`).
- **Root cause:** Vercel is correctly pointed at GitHub `main`, but GitHub `main` is 13 commits behind local.
- **Recommendation:** Push local commits to GitHub — Vercel will auto-deploy the Phase 3C build.

### Finding 3 — `VITE_API_BASE_URL` not set in Vercel environment
**Confidence: Certain (confirmed by localhost:8000 in deployed bundle)**

- **Evidence:** Deployed bundle contains literal `localhost:8000` strings. This only happens when the env var is absent at build time.
- **Root cause:** No `VITE_API_BASE_URL` environment variable was configured in Vercel project settings before or during the build.
- **Impact:** All API calls in the deployed app target `http://localhost:8000/api/v1`, which is unreachable from the browser — causing the `NetworkError`.

### Finding 4 — No backend is deployed; there is no production API URL to point to
**Confidence: High**

- **Evidence:** No production backend URL exists in any source file, `.env.example`, or documentation. The FastAPI backend has only been run locally.
- **Root cause:** The backend has not been hosted yet.
- **Impact:** Even if `VITE_API_BASE_URL` were set, there would be no live backend to point it to.

### Finding 5 — No `vercel.json` SPA rewrite rule exists
**Confidence: Certain**

- **Evidence:** `ls frontend/vercel.json` → not found. `ls vercel.json` → not found.
- **Root cause:** No rewrite configuration has been created.
- **Impact:** When Phase 3C frontend is deployed, navigating directly to `/chat`, `/memories`, `/tasks`, etc. via URL bar or page refresh will return Vercel's default 404 page.

---

## 7. Answers to Key Investigation Questions

| Question | Answer |
|---|---|
| Is Vercel deploying the wrong repository? | **No** — it is deploying `solomon476/AUREN-Personal-AI` as intended |
| Is Vercel deploying the wrong branch? | **No** — it is deploying `main` as configured |
| Is Vercel deploying an older commit? | **Yes** — it is deploying `9babc6d` (GitHub HEAD), not `96c8488` (local HEAD). The 13 Phase 3C commits have never been pushed. |
| Is Vercel building the wrong directory? | **Unknown without Vercel dashboard access** — but the HTML was served, so root directory appears correctly set to `frontend` |
| Is Phase 3C frontend present in GitHub? | **No — zero Phase 3C commits exist on GitHub** |
| Is Phase 3C frontend present only locally? | **Yes — all 13 commits exist only on the local machine** |
| Why does the deployed app show Phase 3A? | Because GitHub has only Phase 3A source (`9babc6d`) and Vercel builds from GitHub |
| Why is the backend unreachable? | `VITE_API_BASE_URL` was not set during Vercel build; bundle falls back to `localhost:8000`; no backend is publicly deployed |
| What exact steps are needed? | See corrective sequence below |

---

## 8. Recommended Corrective Sequence

> [!IMPORTANT]
> These are recommendations only. No action has been taken. Explicit authorization is required before each step.

### Step 1 — Add `frontend/vercel.json` and commit it
```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```
Commit as: `chore(deploy): add Vercel SPA rewrite rule for TanStack Router`

### Step 2 — Set Vercel environment variables (requires Vercel dashboard access)
In Vercel project settings, set for Production environment:
- `VITE_SUPABASE_URL` = your Supabase project URL
- `VITE_SUPABASE_ANON_KEY` = your Supabase anon public key
- `VITE_API_BASE_URL` = URL of deployed FastAPI backend (if/when deployed)

> [!WARNING]
> If the FastAPI backend is not yet deployed to a hosting provider, `VITE_API_BASE_URL` cannot be set to a valid value. The app will work for Supabase auth but all backend API calls (chat, memories, search, reflection, productivity) will fail.

### Step 3 — Deploy the FastAPI backend (prerequisite)
The backend must be deployed to a publicly accessible host before the frontend can function. This is out of scope for the current frontend deployment task and requires separate authorization.

### Step 4 — Push local commits to GitHub
```bash
cd /home/kali/AUREN
git push origin main
```
This will push all 13 Phase 3C commits to GitHub, triggering an automatic Vercel redeploy.

### Step 5 — Verify Vercel build logs
After push, monitor the Vercel deployment to confirm:
- Build uses Phase 3C source
- `VITE_API_BASE_URL` is correctly substituted
- Build succeeds
- No `localhost:8000` appears in the new bundle

### Step 6 — Verify deployed application
Confirm:
- Phase 3C branding appears (not Phase 3A)
- All 13 routes are navigable
- Auth modal appears
- Chat interface loads
- Memory Explorer, Tasks, Projects, etc. are accessible

---

## 9. Unresolved Questions

1. **Is Vercel root directory set to `frontend/`?** — This could not be confirmed without Vercel dashboard access. The deployed app works (HTML is served), which strongly suggests it is correct.
2. **Are Supabase credentials already set in Vercel?** — Cannot be confirmed without dashboard access. The Phase 3A app showed an auth modal, which suggests some Supabase configuration may exist.
3. **Where will the FastAPI backend be hosted?** — No deployment target has been established. This must be resolved to give `VITE_API_BASE_URL` a valid production value.

---

*Report generated: 2026-11-17 | Mode: READ-ONLY investigation | No changes made*
