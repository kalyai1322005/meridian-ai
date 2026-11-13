# Run and deploy Meridian AI for free

You do not need AWS or a credit card. The free setup uses:

| Piece | Free service |
|---|---|
| AI models (chat + embeddings) | Google Gemini API free tier (`GOOGLE_API_KEY`) |
| Vector database | Chroma, stored inside the container (`APP_MODE=local`) |
| Hosting | Render free web service (Docker), no card needed |
| Tests and build | GitHub Actions (free for public repositories) |

> Limits of the free setup: Render's free service has 512 MB RAM, sleeps after 15 idle minutes (the next visit takes about a minute to wake it), and erases uploaded PDFs and the vector index when it restarts. That is fine for a demo; re-upload the files in `sample_docs/`. The app has no sign-in, so upload only the fictional sample documents.
>
> Hugging Face Docker Spaces are no longer free, so this guide does not use them.

## Option A: run on your computer

1. Get a free key at https://aistudio.google.com/apikey.
2. Follow **Quick start** in `README.md` (copy `.env.example` to `.env`, set `GOOGLE_API_KEY`, keep `APP_MODE=local`).

## Option B: put it online with Render

1. Create a free account at https://render.com using **Sign in with GitHub**.
2. Click **New +** then **Web Service**, and choose your `meridian-ai` repository.
3. Set: **Language** = Docker, **Branch** = main, **Instance Type** = Free.
4. Under **Environment Variables** add:
   - `GOOGLE_API_KEY` = your Gemini key
   - `APP_MODE` = `local`
5. Under **Advanced**, set **Health Check Path** to `/api/health`.
6. Click **Deploy Web Service**. The first build takes 5 to 10 minutes. Render then shows a link like `https://meridian-ai.onrender.com`.
7. Every later push to `main` redeploys automatically.
8. Open the link, go to **Index Documents**, upload the PDFs from `sample_docs/`, and ask a question.

Put the Render link in your GitHub repository's **About -> Website** field.

## Troubleshooting

| What you see | What to do |
|---|---|
| Deploy fails with "out of memory" | The free plan has only 512 MB. Use Option A and record a short demo video for your README instead. |
| The page takes a minute to load | The free service was asleep. Wait and refresh. |
| App says `GOOGLE_API_KEY is empty` | Add it under **Environment** in Render, then redeploy. |
| "model not found" | Set `LOCAL_LLM_MODEL_NAME` to a current model from https://ai.google.dev/gemini-api/docs/models |
| Answers are gone after a while | The service restarted. Upload the sample PDFs again. |

The paid AWS path is still in the repository (`DEPLOY.md`, `infrastructure/aws/`) and only runs when you start it by hand.
