# AUREN Phase 4B Diagnostic: Production Projects API Failure

> [!IMPORTANT]
> **Mode:** STRICTLY READ-ONLY Investigation  
> **Target Production URL:** `https://frontend-alpha-steel-64.vercel.app/projects`  
> **Observed User Experience:** Projects page renders, displays red banner `Failed to load projects. Please try again.`, sidebar shows `Sign In`.  
> **Investigation Date:** 17 November 2026

---

## 1. Executive Summary

| Diagnostic Question | Finding | Supporting Evidence |
|---|---|---|
| **What exact request fails?** | `GET http://localhost:8000/api/v1/projects?page=1&page_size=20` | Headless browser network trace captures `net::ERR_CONNECTION_REFUSED` |
| **Why does it request localhost:8000?** | `VITE_API_BASE_URL` was not set in Vercel environment variables during the build; Vite baked the fallback `http://localhost:8000/api/v1` into the bundle | `curl https://frontend-alpha-steel-64.vercel.app/assets/index-Bizfs9nD.js \| grep "http://localhost:8000"` |
| **Is the browser authenticated?** | **No.** Guest session (`localStorage` has 0 keys; sidebar displays `Sign In`) | Headless browser evaluation of `localStorage` returns `[]` |
| **Does the API contract match?** | **Yes, 100% match.** The query parameters, pagination, and response model match the FastAPI endpoint | [frontend/src/api/productivity.ts#L233](file:///home/kali/AUREN/frontend/src/api/productivity.ts#L233) vs [backend/app/api/v1/projects.py#L55](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L55) |
| **Is this failure expected?** | **YES.** As documented in Phase 3C and Phase 4A, the FastAPI backend has not yet been deployed to a public cloud host. | Verified |
| **Is there an additional frontend defect?** | **YES.** `useProjects` fires unconditionally even when unauthenticated (`enabled` check missing). When the backend is deployed, an unauthenticated user will still see `Failed to load projects` due to HTTP 401 instead of a login prompt. | [frontend/src/hooks/useProductivity.ts#L164](file:///home/kali/AUREN/frontend/src/hooks/useProductivity.ts#L164) |

---

## 2. Technical Inspection of Components & API Services

### 2.1 The Frontend UI Component
- **Component File:** [frontend/src/features/projects/ProjectsView.tsx](file:///home/kali/AUREN/frontend/src/features/projects/ProjectsView.tsx#L41)
- **Data Hook Invocation:**
  ```tsx
  const { data: projectsData, isLoading, error } = useProjects({
    status: selectedStatus || undefined,
    query: searchQuery || undefined,
    page,
    page_size: 20,
  });
  ```
- **Error Render Condition (Lines 149–154):**
  ```tsx
  ) : error ? (
    <div className="p-4 bg-red-950/40 border border-red-800/80 rounded-lg text-sm text-red-300 flex items-center space-x-2">
      <AlertCircle className="w-5 h-5" />
      <span>Failed to load projects. Please try again.</span>
    </div>
  ```
  When `useProjects` fails (after React Query's standard 3 retry attempts), `error` becomes non-null, triggering this red alert banner.

### 2.2 The React Query Hook
- **Hook File:** [frontend/src/hooks/useProductivity.ts#L153-L169](file:///home/kali/AUREN/frontend/src/hooks/useProductivity.ts#L153-L169)
  ```typescript
  export function useProjects(
    params?: {
      status?: string;
      goal_id?: string;
      query?: string;
      page?: number;
      page_size?: number;
    },
    userId?: string
  ) {
    const currentUserId = useCurrentUserId(userId);
    return useQuery({
      queryKey: [...PRODUCTIVITY_KEYS.projects(currentUserId), params],
      queryFn: () => getProjects(params),
      staleTime: 1000 * 30,
    });
  }
  ```
  Notice: `enabled` is omitted. React Query defaults to `enabled: true`, causing the query to fire immediately upon component mount regardless of whether the user is logged in.

### 2.3 The Productivity API Service
- **Service File:** [frontend/src/api/productivity.ts#L233-L249](file:///home/kali/AUREN/frontend/src/api/productivity.ts#L233-L249)
  ```typescript
  export async function getProjects(params?: { ... }): Promise<ProjectListResponse> {
    const query = new URLSearchParams();
    if (params?.status) query.set('status', params.status);
    if (params?.page) query.set('page', String(params.page));
    if (params?.page_size) query.set('page_size', String(params.page_size));

    const qs = query.toString();
    return apiClient.get<ProjectListResponse>(`/projects${qs ? `?${qs}` : ''}`);
  }
  ```

### 2.4 The Underlying HTTP Client
- **Client File:** [frontend/src/api/client.ts#L7-L47](file:///home/kali/AUREN/frontend/src/api/client.ts#L7-L47)
  ```typescript
  const API_BASE_URL =
    import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';

  async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const url = `${API_BASE_URL.replace(/\/$/, '')}/${endpoint.replace(/^\//, '')}`;
    ...
    if (supabase) {
      try {
        const { data: { session } } = await supabase.auth.getSession();
        if (session?.access_token && !headers.has('Authorization')) {
          headers.set('Authorization', `Bearer ${session.access_token}`);
        }
      } catch { }
    }

    const response = await fetch(url, { ...options, headers });
  ```

---

## 3. Live Production Browser Evidence (Headless Playwright Trace)

A headless Chromium instance was dispatched to `https://frontend-alpha-steel-64.vercel.app/projects` to record actual live network activity, localStorage state, and console telemetry.

### 3.1 Network Requests Captured

```json
[
  {
    "url": "https://frontend-alpha-steel-64.vercel.app/projects",
    "method": "GET",
    "status": 200
  },
  {
    "url": "http://localhost:8000/api/v1/projects?page=1&page_size=20",
    "method": "GET",
    "headers": {
      "content-type": "application/json",
      "user-agent": "Mozilla/5.0 ... HeadlessChrome"
    }
  },
  {
    "url": "http://localhost:8000/api/v1/goals?page_size=100",
    "method": "GET",
    "headers": {
      "content-type": "application/json"
    }
  }
]
```

### 3.2 Network Failures Captured

```json
[
  {
    "url": "http://localhost:8000/api/v1/projects?page=1&page_size=20",
    "method": "GET",
    "failure": {
      "errorText": "net::ERR_CONNECTION_REFUSED"
    }
  },
  {
    "url": "http://localhost:8000/api/v1/goals?page_size=100",
    "method": "GET",
    "failure": {
      "errorText": "net::ERR_CONNECTION_REFUSED"
    }
  }
]
```

### 3.3 Browser Console Telemetry

```
[error] Failed to load resource: net::ERR_CONNECTION_REFUSED (http://localhost:8000/api/v1/projects?page=1&page_size=20)
[error] Failed to load resource: net::ERR_CONNECTION_REFUSED (http://localhost:8000/api/v1/goals?page_size=100)
```

### 3.4 Client Authentication State (`localStorage`)

```json
[]
```
`localStorage` is completely empty. No Supabase session keys (`sb-<project-ref>-auth-token`) exist.

---

## 4. Root Cause Analysis: Evaluation of Hypotheses

| Hypothesis | Evaluation | Verdict | Technical Explanation |
|---|---|---|---|
| **1. Missing backend deployment** | Verified | **PRIMARY CAUSE** | The FastAPI backend has never been deployed to a public cloud host (e.g. Railway). There is no live backend server running on the internet. |
| **2. Incorrect API base URL** | Verified | **PRIMARY CAUSE** | Because `VITE_API_BASE_URL` was not configured in Vercel project environment variables, the Vite build statically bundled the local development default: `http://localhost:8000/api/v1`. The browser tries to connect to port 8000 on the visitor's local machine, which rejects the TCP connection (`net::ERR_CONNECTION_REFUSED`). |
| **3. Missing authentication** | Verified | **SECONDARY CAUSE / UX FLAW** | The browser session has no Supabase login token. While the current failure is caught at the transport layer (`ERR_CONNECTION_REFUSED`), even if the backend were reachable at `localhost:8000`, the FastAPI endpoint [projects.py#L55](file:///home/kali/AUREN/backend/app/api/v1/projects.py#L55) requires `current_user = Depends(get_current_user)` and would reject the unauthenticated request with **HTTP 401 Unauthorized**. |
| **4. CORS rejection** | Rejected | **NOT A CAUSE** | The request fails at TCP connection establishment (`ERR_CONNECTION_REFUSED`) before any HTTP request or CORS preflight is transmitted. |
| **5. Incorrect endpoint or request parameters** | Rejected | **NOT A CAUSE** | The request path `/projects?page=1&page_size=20` and query schema match the backend FastAPI router perfectly. |
| **6. Backend authorization or database failure** | Rejected | **NOT A CAUSE** | No request ever reached any backend instance. |

---

## 5. API Contract Verification (Frontend vs Backend)

A rigorous contract comparison between the frontend consumer and backend provider proves that the request schema is completely aligned:

| Contract Dimension | Frontend Specification (`api/productivity.ts`) | Backend Specification (`api/v1/projects.py`) | Parity |
|---|---|---|---|
| **HTTP Verb** | `GET` | `@router.get("")` | ✅ Identical |
| **Route Path** | `${API_BASE_URL}/projects` | `/api/v1/projects` (mounted at `/projects` with prefix `/api/v1`) | ✅ Identical |
| **Query Parameter: status** | `query.set('status', params.status)` | `status: Optional[str] = Query(default=None)` | ✅ Identical |
| **Query Parameter: page** | `query.set('page', String(params.page))` | `page: int = Query(default=1, ge=1)` | ✅ Identical |
| **Query Parameter: page_size** | `query.set('page_size', String(params.page_size))` | `page_size: int = Query(default=20, ge=1, le=100)` | ✅ Identical |
| **Response Schema** | `items: Project[]`, `total: number`, `page: number`, `page_size: number`, `total_pages: number` | `ProjectListResponse(items=[...], total=..., page=..., page_size=..., total_pages=...)` | ✅ Identical |

There is **zero contract divergence**. Once the backend is deployed and pointed to by `VITE_API_BASE_URL`, valid requests will deserialize seamlessly.

---

## 6. Secondary Product & UX Defect Identified

While the primary failure is the missing backend, a secondary product defect exists in the frontend architecture:

### Unauthenticated Query Firing
In [frontend/src/features/projects/ProjectsView.tsx](file:///home/kali/AUREN/frontend/src/features/projects/ProjectsView.tsx), the page renders freely for unauthenticated visitors.
However, [frontend/src/hooks/useProductivity.ts#L164](file:///home/kali/AUREN/frontend/src/hooks/useProductivity.ts#L164) executes `useQuery` unconditionally:
```typescript
const currentUserId = useCurrentUserId(userId); // returns 'anonymous' when unauthenticated
return useQuery({
  queryKey: [...PRODUCTIVITY_KEYS.projects(currentUserId), params],
  queryFn: () => getProjects(params),
  staleTime: 1000 * 30,
  // MISSING: enabled: Boolean(auth?.user)
});
```

### Future Impact if Not Addressed
When the backend is deployed to Railway and `VITE_API_BASE_URL` is set:
1. An unauthenticated visitor navigates to `https://frontend-alpha-steel-64.vercel.app/projects`.
2. The browser successfully reaches the backend.
3. The backend returns `HTTP 401 Unauthorized` (`detail: "Missing or invalid authentication credentials."`).
4. React Query sets `error`, and `ProjectsView` will **still display the red banner: `Failed to load projects. Please try again.`**
5. **Expected UX Behavior:** The UI should either:
   - Guard protected routes (redirecting anonymous visitors to `/login` or displaying a prompt: *"Please sign in to view your projects"*).
   - Only execute `useProjects` when `Boolean(auth?.user)` is true (`enabled: Boolean(auth?.user)`).

---

## 7. Conclusions & Recommended Remediation

### 7.1 Is this failure expected?
**YES.** This failure is the direct, expected physical consequence of the backend not yet being deployed to a public cloud host. The frontend bundle was compiled with the development fallback `http://localhost:8000/api/v1`.

### 7.2 Required Remediation Steps

1. **Deploy Backend (Phase 4B.2):**
   - Deploy the FastAPI backend and memory worker to Railway using the deployment configuration verified in Phase 4B.1.
   - Obtain the public backend domain: `https://<backend-domain>.up.railway.app`.
2. **Update Vercel Configuration:**
   - In Vercel Project Settings > Environment Variables, configure:
     ```
     VITE_API_BASE_URL = https://<backend-domain>.up.railway.app/api/v1
     ```
   - **Trigger a new Vercel production build** to bake the new URL into the JavaScript bundle.
3. **Frontend UX Improvement (Future Non-Blocking):**
   - In `frontend/src/hooks/useProductivity.ts`, add `enabled: Boolean(auth?.user)` to `useProjects`, `useTasks`, `useGoals`, and `useDashboardQuery`.
   - In `ProjectsView.tsx`, display an unauthenticated state with a prominent *"Sign In to Access Projects"* CTA when `!auth?.user`.

---

*Report generated: 2026-11-17 · Commit: `186d1ca` · Conversation: `b7cea535-b917-4f28-9c42-2a03574d18ce`*
