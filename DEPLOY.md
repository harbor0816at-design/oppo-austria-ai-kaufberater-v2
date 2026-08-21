# Deployment

Use the same GitHub repository for two Vercel projects.

## 1. Backend Vercel project

- Root Directory: `backend`
- Project name suggestion: `oppo-austria-ai-kaufberater`

Required environment variables:

```text
APP_ENV=production
ADMIN_API_KEY=<long random secret>
DATABASE_URL=<PostgreSQL connection string>
DEEPSEEK_API_KEY=<DeepSeek API key>
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
CORS_ORIGINS=https://oppo-austria-ai-kaufberater-web.vercel.app
```

Optional:

```text
REDIS_URL=<Redis URL>
BRAVE_SEARCH_API_KEY=<Brave Search key for Source_A>
BLOB_READ_WRITE_TOKEN=<created automatically after connecting a public Vercel Blob store>
```

After deployment verify:

```text
GET /
GET /healthz
GET /api/ui/hero-slides
GET /api/admin/ai-health   (Header: X-Admin-Key)
```

## 2. Frontend Vercel project

- Root Directory: `frontend`
- Project name suggestion: `oppo-austria-ai-kaufberater-web`

Environment variable:

```text
ASSISTANT_API_BASE_URL=https://oppo-austria-ai-kaufberater.vercel.app
```

Do not set a forced demo SKU. The assistant should select from all launched Source_B products.

## 3. Add Source_B products

Open:

```text
https://<frontend-domain>/admin/
```

Enter `ADMIN_API_KEY`, paste one ProductFact JSON object or an array, then upload. The backend validates every field before saving and refreshes Redis immediately.

## 4. Hero slides

The consumer page automatically loads `GET /api/ui/hero-slides`. Admin changes become visible after refresh. If the database is empty or temporarily unavailable, three local fallback slides are returned.

## 5. Hero media upload

Connect a **public Vercel Blob store** to the backend project, then use the admin upload control. Without Blob, paste an existing public image/video URL instead.
