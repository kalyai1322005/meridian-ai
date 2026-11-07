# Putting Meridian AI on AWS

This page explains how to run the app on the internet and use document Q&A on **Amazon Web Services (AWS)**. It is written step by step. If a word is new, a short explanation follows it.

**Time:** about 30 minutes of work. Most of it is clicking; the first deploy then waits about 10 minutes.
**Money:** read [Costs](#costs-read-this-first) before you start.

---

## The big picture

You do three things by hand, **once**:

1. Create an **AWS account** and a **budget alert**.
2. Create one **CloudFormation stack** from `infra/aws-bootstrap.yaml`. It makes the storage, the vector database, the secret, the container registry and the permissions (including a "deploy role" for GitHub).
3. Tell **GitHub** the deploy role and your Gemini key.

After that, every push to `main` runs `.github/workflows/deploy.yml`: it runs the tests, builds the Docker image, pushes it to AWS and updates the running service.

| Part of the app | AWS service |
|---|---|
| Web server (the Docker box) | **Amazon ECS Express Mode** (runs on Fargate behind a load balancer, gives you an `https://…on.aws` address) |
| Document Q&A database (vectors) | **Amazon S3 Vectors** |
| Original PDFs and logs | **Amazon S3** |
| Embeddings (text → numbers) | **Amazon Bedrock**, Titan Text Embeddings V2 |
| Chat model | Gemini API (your key), or Amazon Bedrock if you choose |
| Keys and passwords | **AWS Secrets Manager** |
| Container images | **Amazon ECR** |
| Logs | **Amazon CloudWatch Logs** |
| Permissions | **IAM** roles (no access keys are stored anywhere) |

> **Why not AWS App Runner?** It is the closest match to Google Cloud Run, but AWS stopped accepting new customers for it, so this project uses ECS Express Mode, AWS's replacement for simple container hosting.

---

## Costs (read this first)

Prices change; check https://aws.amazon.com/pricing/ before relying on any number here.

| Service | How you are charged |
|---|---|
| **ECS Express Mode** | You pay for the running container (Fargate) **and the load balancer it creates, by the hour, even when nobody uses the app**. This is the main cost. |
| S3 Vectors | By storage and requests: for a few documents this is usually cents. There is no always-on server. |
| S3, ECR, Secrets Manager, CloudWatch | Cents for this project |
| Bedrock embeddings | Per text processed: tiny for a few PDFs |
| Gemini API (the chat model) | Has a free tier. Free-tier content may be used by Google to improve its products, so use only the sample documents. |

**New AWS accounts** get free-plan credits and a limited free period: see https://aws.amazon.com/free/ for the current terms.

**Set a budget alert first** (step 2 below). It emails you as spending grows. It does **not** stop the spending: switch things off yourself (see [Switch everything off](#switch-everything-off)).

---

## Step by step

### Step 1 · Get a Gemini API key

1. Go to https://aistudio.google.com/apikey and sign in.
2. Click **Create API key** and copy it.
3. Treat it like a password: never post it or put it in Git.

(Prefer to avoid Google entirely? See [Use Bedrock for the chat model too](#optional-use-bedrock-for-the-chat-model-too).)

### Step 2 · Create your AWS account and a budget alert

1. Create an account at https://aws.amazon.com/ and sign in to the console. Choose one **region** and stay in it for everything (the examples use `us-east-1`).
2. Console → **Billing and Cost Management → Budgets → Create budget**. Choose a monthly cost budget, for example **$20**, and add your email for alerts.

### Step 3 · Install and sign in to the AWS CLI (only needed for the commands below)

Install AWS CLI v2: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html. Then:

```bash
aws configure sso          # or: aws configure   (use an IAM user with administrator access for this one-time setup)
aws sts get-caller-identity   # shows the account you are signed in to
```

### Step 4 · Create the stack (the one-time setup)

From the project folder:

```bash
aws cloudformation deploy \
  --region us-east-1 \
  --stack-name meridian-ai \
  --template-file infra/aws-bootstrap.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides GitHubRepo=YOUR_GITHUB_USER/meridian-ai
```

- Change `GitHubRepo` to **your own** `owner/repo` (the repository that will run the workflow).
- If your account already has a GitHub OIDC provider (error "provider already exists"), add `CreateGitHubOidcProvider=false ExistingGitHubOidcProviderArn=arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com`.
- The stack asks for the vector size `EmbeddingDimensions` (default `1024`). It cannot be changed later without creating a new index.

Then store your Gemini key in the secret the stack created:

```bash
aws secretsmanager put-secret-value \
  --region us-east-1 \
  --secret-id meridian-ai/GOOGLE_API_KEY \
  --secret-string "PASTE_YOUR_GEMINI_KEY"
```

Print the values you need next:

```bash
aws cloudformation describe-stacks --region us-east-1 --stack-name meridian-ai \
  --query "Stacks[0].Outputs[].[OutputKey,OutputValue]" --output table
```

### Step 5 · Put the code on your own GitHub

The workflow runs from **your** GitHub copy. On this repository's page click **Fork** (skip this if you are already working in your own repository). Open the **Actions** tab and enable workflows if GitHub asks.

### Step 6 · Tell GitHub about AWS

In your repository: **Settings → Secrets and variables → Actions**.

| Kind | Name | Value |
|---|---|---|
| **Secret** | `AWS_ROLE_ARN` | The `DeployRoleArn` output from step 4 |
| **Variable** | `AWS_REGION` | `us-east-1` (the region you used) |
| **Variable** | `AWS_STACK_NAME` | `meridian-ai` |

No access keys are stored: GitHub proves its identity to AWS with short-lived tokens (OIDC), and only runs on the `main` branch can use the role.

### Step 7 · Run the workflow

**Actions → Deploy to AWS (ECS Express Mode) → Run workflow.** (It also starts by itself whenever you push to `main`.)

| Job | In plain words |
|---|---|
| Backend tests | Runs the automated tests |
| Sign in | GitHub logs in to AWS with the deploy role |
| Build | Packs the app into a Docker box and uploads it to ECR |
| Deploy | Creates the service on the first run (this also creates the load balancer, a few minutes), or rolls out the new image on later runs, then checks `/api/health` |

The last lines of the log (and the run summary) show your app's address, like `https://xxxx.ecs.us-east-1.on.aws`. If a step fails, read the last lines and re-run: it is safe to run again.

### Step 8 · Use it

- **On the internet:** open the address. Upload the PDFs from `sample_docs/` and ask questions.
- **From your own computer** (using the AWS storage and vector database): put these in your `.env` (use the bucket names from step 4), sign in with `aws sso login` or `aws configure`, and start the app as in the README.

```
APP_MODE=cloud
AWS_REGION=us-east-1
S3_BUCKET_NAME=<DocumentsBucketName output>
S3_PREFIX=uploads/
S3_VECTORS_BUCKET_NAME=<VectorBucketName output>
S3_VECTORS_INDEX_NAME=meridian-docs
GOOGLE_API_KEY=<your Gemini key>
```

> **Careful:** the public address has **no login**. Anyone who finds it can use your Gemini quota and upload files. The service is capped at 3 copies to limit the damage. Do not upload private documents, and switch it off when you are done.

### Optional: use Bedrock for the chat model too

To remove the Gemini key completely, enable a chat model in the Bedrock console for your region, then add the repository **variables** `LLM_PROVIDER=bedrock` and `BEDROCK_LLM_MODEL_ID=<model or inference-profile ID>` and re-run the workflow. Locally, set the same two values in `.env`. (Local mode still needs the Gemini key for its embeddings.)

---

## Switch everything off

Do this when you finish. It stops the charges.

**The web server and load balancer (the part that costs by the hour):**

```bash
aws ecs delete-express-gateway-service --region us-east-1 \
  --service-arn arn:aws:ecs:us-east-1:<account-id>:service/default/meridian-ai
```

**Everything else:** empty the two S3 buckets, then delete the stack. (CloudFormation cannot delete a bucket that still has files in it.)

```bash
aws s3 rm s3://<DocumentsBucketName> --recursive
# the vector index and vector bucket are deleted by the stack; if that fails because the index still has
# data, delete the index first:
aws s3vectors delete-index --region us-east-1 --vector-bucket-name <VectorBucketName> --index-name meridian-docs
aws ecr delete-repository --region us-east-1 --repository-name meridian-ai --force
aws cloudformation delete-stack --region us-east-1 --stack-name meridian-ai
```

Also remove the GitHub secret and variables. **Check:** next day, Billing → Cost Explorer should show the daily cost near zero.

---

## If something goes wrong

| What you see | Likely cause and fix |
|---|---|
| `AccessDenied` / "not authorized" from S3, S3 Vectors or Bedrock | Wrong account or region. Run `aws sts get-caller-identity`; for the app on ECS, check the task role `meridian-ai-task` |
| "Could not connect to the endpoint URL" | The region in `AWS_REGION` does not offer the service, or does not match the stack |
| Bedrock embeddings: "model access denied" / "not authorized to invoke" | Open Bedrock in the console for this region and make sure Titan Text Embeddings V2 is available to your account |
| Workflow fails at "Authenticate to AWS" | `AWS_ROLE_ARN` secret wrong, the workflow is not running on `main`, or `GitHubRepo` in the stack is not this repository |
| `Unable to assume the service linked role` on the first deploy | AWS roles take a minute to spread. Wait a minute and re-run the workflow |
| `ValidationException … dimension` | The index size and `BEDROCK_EMBEDDING_DIMENSIONS` differ. Create a new stack/index with the size you want |
| App opens but answers fail | Open CloudWatch Logs → `/ecs/meridian-ai`; check the secret holds your real Gemini key |
| "model not found" | Set `LLM_MODEL_NAME` to a current model: https://ai.google.dev/gemini-api/docs/models |
| First request after a quiet period is slow | The container is warming up |
