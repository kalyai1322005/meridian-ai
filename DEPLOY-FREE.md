# Run and deploy Meridian AI for free

You do not need AWS or a credit card. The free setup uses:

| Piece | Free service |
|---|---|
| AI models (chat + embeddings) | Google Gemini API free tier (`GOOGLE_API_KEY`) |
| Vector database | Chroma, stored inside the container (`APP_MODE=local`) |
| Hosting | Hugging Face Spaces, free CPU, Docker |
| Tests and build | GitHub Actions (free for public repositories) |

> Limits of the free setup: the Space sleeps when idle and wakes in about a minute, and uploaded PDFs and the vector index are erased when it restarts. That is fine for a demo; re-upload the files in `sample_docs/`. The app has no sign-in, so upload only the fictional sample documents.

## Option A: run on your computer

1. Get a free key at https://aistudio.google.com/apikey.
2. Follow **Quick start** in `README.md` (copy `.env.example` to `.env`, set `GOOGLE_API_KEY`, keep `APP_MODE=local`).

## Option B: put it online with Hugging Face Spaces

1. Create a free account at https://huggingface.co.
2. **New Space**: name it `meridian-ai`, choose **Docker** as the SDK, **Blank** template, **CPU basic (free)**, and make it Public.
3. In the Space, open **Settings -> Variables and secrets** and add a **secret** named `GOOGLE_API_KEY` (your Gemini key).
4. On huggingface.co open **Settings -> Access Tokens**, create a token with **Write** permission, and copy it.
5. In your GitHub repository open **Settings -> Secrets and variables -> Actions**:
   - **Secret** `HF_TOKEN` = the token from step 4
   - **Variable** `HF_SPACE` = `your-hf-username/meridian-ai`
6. Open **Actions -> Deploy to Hugging Face Space (free) -> Run workflow**. After it finishes, the Space builds (about 5 to 10 minutes the first time). Every later push to `main` redeploys automatically.
7. Open `https://huggingface.co/spaces/your-hf-username/meridian-ai`, go to **Index Documents**, upload the PDFs from `sample_docs/`, and ask a question.

Put the Space link in your GitHub repository's **About -> Website** field so recruiters can click it.

## Troubleshooting

| What you see | What to do |
|---|---|
| The workflow says "skipping" | `HF_TOKEN` or `HF_SPACE` is missing. Check the names exactly. |
| `git push` is rejected (403) | The token needs **Write** permission and the Space name in `HF_SPACE` must match exactly. |
| App says `GOOGLE_API_KEY is empty` | Add the secret in the Space settings, then **Restart** the Space. |
| "model not found" | Set `LOCAL_LLM_MODEL_NAME` as a Space variable to a current model from https://ai.google.dev/gemini-api/docs/models |
| Answers are gone after a while | The free Space restarted. Upload the sample PDFs again. |

The paid AWS path is still in the repository (`DEPLOY.md`, `infrastructure/aws/`) and only runs when you start it by hand.
