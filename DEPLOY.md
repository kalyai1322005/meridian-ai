# Deploy Meridian AI to AWS (beginner guide)

This project keeps its local mode and adds an AWS cloud mode. AWS hosts the app in ECS Fargate, stores PDFs and archived logs in S3, searches document vectors in OpenSearch Serverless, and runs chat and embedding models through Amazon Bedrock.

## Before you start

- An AWS account with permission to create IAM roles, networking, ECS, S3, ECR, Bedrock and OpenSearch Serverless resources.
- A GitHub account with this repository copied to your own account. Keep the copy private if you will use real documents.
- Billing enabled. Set an AWS Budget alert before deploying. ECS Fargate and the public load balancer run while the service exists. OpenSearch Serverless charges depend on collection type, capacity, and use; review its regional [pricing](https://aws.amazon.com/opensearch-service/pricing/) before deploying. Deleting the stack stops the service, but the S3 bucket is intentionally retained so documents are not accidentally erased.
- The deployment uses `us-east-1` by default because the configured Bedrock model IDs are available there. In the Bedrock console, confirm that Amazon Nova Lite and Titan Text Embeddings V2 can be used in your account and selected region.

The web app is public over HTTP and has no sign-in. Use sample documents only until you add authentication and HTTPS. Do not upload private or sensitive documents. The OpenSearch collection has standby replicas disabled to reduce demo cost; enable redundancy before production use. Changing this setting requires replacing the collection.

## Step 1: Make a copy of the repository

On GitHub, open your copy of `meridian-ai` and make sure the default branch is named `main`. The deploy workflow runs after a push to `main`, or when you manually start it from **Actions → Deploy to AWS ECS → Run workflow**.

## Step 2: Create a GitHub-to-AWS connection (OIDC)

OIDC lets GitHub request short-lived AWS credentials for a workflow. You do not create or store an AWS access key.

1. In the AWS Console, open **IAM → Identity providers → Add provider**.
2. Choose **OpenID Connect**. Set the provider URL to `https://token.actions.githubusercontent.com` and audience to `sts.amazonaws.com`.
3. Open **IAM → Roles → Create role → Web identity**. Select the GitHub provider and `sts.amazonaws.com` audience.
4. In the trust relationship, restrict `token.actions.githubusercontent.com:sub` to `repo:YOUR_GITHUB_NAME/meridian-ai:ref:refs/heads/main` (replace the owner and repository with your copy). This limits the role to workflows from that repository's main branch. An example is in `infrastructure/aws/github-oidc-trust-policy.example.json`.
5. Give the role a clear name such as `MeridianGitHubDeploy`.
6. Create an IAM policy from `infrastructure/aws/github-deploy-policy.example.json`: replace `YOUR_ACCOUNT_ID` and `YOUR_REGION`, then attach it to the GitHub role. It allows the workflow to create the ECR repository and CloudFormation resources used by this project, and to pass only `meridian-ai-*` roles to ECS tasks. The infrastructure permissions are broad within the listed AWS services, so use a separate learning account and do not reuse this role for other repositories. An AWS administrator may need to create the role and policy for you.
7. Copy the role's ARN. It looks like `arn:aws:iam::123456789012:role/MeridianGitHubDeploy`.

## Step 3: Add one GitHub secret and one variable

In your GitHub copy, open **Settings → Secrets and variables → Actions**.

- Under **Secrets**, add `AWS_ROLE_ARN` with the role ARN from Step 2.
- Under **Variables**, add `AWS_REGION` with `us-east-1`.

The application does not need an AWS secret key or Gemini key in cloud mode. ECS gives it a task role with access to only its S3 bucket, Bedrock inference, and its OpenSearch collection.

## Step 4: Deploy

Open **Actions → Deploy to AWS ECS → Run workflow** and choose **Run workflow**. The first run builds the Docker image and creates the network, S3 bucket, OpenSearch Serverless collection, ECS service, and load balancer. OpenSearch may take several minutes to become ready. Later runs publish a new image and update the service.

When the workflow completes, open its last step and copy the printed application URL. Open that address, then use **Document Ingestion** to upload the example PDFs from `sample_docs/` and ask a question.

## What each AWS service does

| AWS service | Role in this app |
|---|---|
| ECS Fargate | Runs the Docker container without you managing a server |
| Application Load Balancer | Gives the app a stable public address and checks `/api/health` |
| ECR | Stores versioned Docker images built by GitHub Actions |
| S3 | Keeps uploaded PDFs and archived task logs |
| OpenSearch Serverless | Stores and searches document embeddings; standby replicas are disabled in this learning setup |
| Amazon Bedrock | Runs Nova Lite chat and Titan Text Embeddings V2 |
| IAM task role | Gives the running app AWS permissions without stored keys |
| CloudWatch Logs | Collects the app's live container logs |

## Common problems

| What you see | What to check |
|---|---|
| Workflow fails at AWS credentials | Check that `AWS_ROLE_ARN` is the role ARN and the IAM trust relationship names the exact GitHub owner, repository, `main` branch, and `sts.amazonaws.com` audience. |
| Access denied during stack creation | The GitHub deployment role needs the AWS resource permissions listed in Step 2 and `iam:PassRole` for the ECS roles. |
| Bedrock returns access denied or model unavailable | In the AWS Console, confirm that Nova Lite and Titan Text Embeddings V2 are available to your account in the selected region. Check `AWS_REGION` and model IDs in the workflow/template. |
| OpenSearch returns 401/403 | Wait a few minutes after the first stack creation. Check the stack events and that its data policy names the task role. |
| The app URL loads but document questions fail | Open **CloudWatch → Log groups → `/ecs/meridian-ai`** and inspect the newest log stream. Confirm the S3 and OpenSearch outputs in the CloudFormation stack. |
| Stack creation fails | Open **CloudFormation → Stacks → meridian-ai → Events** and read the first `CREATE_FAILED` event. A bucket-name conflict is unlikely because the name includes your account ID and region. |

## Stop AWS charges and clean up

To stop the running service and remove the load balancer, networking and OpenSearch collection, delete the CloudFormation stack named `meridian-ai` from **CloudFormation → Stacks**. Review the stack resources before confirming. The S3 bucket has a retain policy so deleting the stack will not erase uploaded PDFs or archived logs. Empty the bucket and delete it separately only when you are sure you no longer need the files. Also delete the ECR repository `meridian-ai` if you no longer need its container images.

Check **Billing → Bills** the next day to confirm usage has stopped. Deleting the stack does not delete the GitHub OIDC provider or deployment IAM role; remove those under IAM if you no longer use this workflow.

## Run locally

Local mode stays the same: install the project's dependencies, copy `.env.example` to `.env`, add a Gemini API key, keep `APP_MODE=local`, then follow the local run commands in `README.md`. AWS cloud mode on a developer computer uses the normal AWS credential chain (`aws configure` or `aws sso login`) plus `AWS_REGION`, `S3_BUCKET_NAME`, and `OPENSEARCH_URL`; use least-privilege AWS credentials and never commit local `.env` files.
