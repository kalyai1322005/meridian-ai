#!/usr/bin/env bash
# Create or update the Meridian AI service on Amazon ECS Express Mode.
#
# Called by .github/workflows/deploy.yml after the Docker image is pushed, but you can also run it
# from your own terminal (needs the AWS CLI v2 logged in to the right account, plus jq and curl):
#
#   AWS_REGION=us-east-1 AWS_STACK_NAME=meridian-ai IMAGE_TAG=latest infra/deploy-service.sh
#
# Everything else (bucket names, role ARNs, image repository, secret) is read from the outputs of
# the CloudFormation stack created from infra/aws-bootstrap.yaml.
set -euo pipefail

: "${AWS_REGION:?set AWS_REGION}"
: "${AWS_STACK_NAME:?set AWS_STACK_NAME (the CloudFormation stack made from infra/aws-bootstrap.yaml)}"
: "${IMAGE_TAG:?set IMAGE_TAG (the tag that was pushed to ECR)}"
SERVICE_NAME="${SERVICE_NAME:-meridian-ai}"
LLM_MODEL_NAME="${LLM_MODEL_NAME:-gemini-3.8-flash}"
# Optional: LLM_PROVIDER=bedrock BEDROCK_LLM_MODEL_ID=<model or inference-profile id>

export AWS_PAGER=""
stack_output() {
  aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$AWS_STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
IMAGE="$(stack_output RepositoryUri):${IMAGE_TAG}"
EXECUTION_ROLE="$(stack_output TaskExecutionRoleArn)"
INFRA_ROLE="$(stack_output InfrastructureRoleArn)"
TASK_ROLE="$(stack_output TaskRoleArn)"
SECRET_ARN="$(stack_output SecretArn)"
LOG_GROUP="$(stack_output LogGroupName)"

# Environment variables for the container. Optional ones are only added when set.
ENV_JSON="$(jq -n \
  --arg region "$AWS_REGION" \
  --arg docs "$(stack_output DocumentsBucketName)" \
  --arg vbucket "$(stack_output VectorBucketName)" \
  --arg vindex "$(stack_output VectorIndexName)" \
  --arg dims "$(stack_output EmbeddingDimensions)" \
  --arg llm "$LLM_MODEL_NAME" \
  --arg provider "${LLM_PROVIDER:-}" \
  --arg bedrock_model "${BEDROCK_LLM_MODEL_ID:-}" \
  '[
     {name:"APP_MODE", value:"cloud"},
     {name:"ENVIRONMENT", value:"production"},
     {name:"AWS_REGION", value:$region},
     {name:"S3_BUCKET_NAME", value:$docs},
     {name:"S3_PREFIX", value:"uploads/"},
     {name:"S3_VECTORS_BUCKET_NAME", value:$vbucket},
     {name:"S3_VECTORS_INDEX_NAME", value:$vindex},
     {name:"BEDROCK_EMBEDDING_DIMENSIONS", value:$dims},
     {name:"LLM_MODEL_NAME", value:$llm}
   ]
   + (if $provider != "" then [{name:"LLM_PROVIDER", value:$provider}] else [] end)
   + (if $bedrock_model != "" then [{name:"BEDROCK_LLM_MODEL_ID", value:$bedrock_model}] else [] end)')"

CONTAINER_JSON="$(jq -n --arg image "$IMAGE" --arg group "$LOG_GROUP" --arg secret "$SECRET_ARN" --argjson env "$ENV_JSON" '{
  image: $image,
  containerPort: 8080,
  awsLogsConfiguration: {logGroup: $group, logStreamPrefix: "ecs"},
  environment: $env,
  secrets: [{name: "GOOGLE_API_KEY", valueFrom: $secret}]
}')"
SCALING_JSON='{"minTaskCount":1,"maxTaskCount":3,"autoScalingMetric":"AVERAGE_CPU","autoScalingTargetValue":60}'

SERVICE_ARN="arn:aws:ecs:${AWS_REGION}:${ACCOUNT_ID}:service/default/${SERVICE_NAME}"
INPUT_FILE="$(mktemp)"
trap 'rm -f "$INPUT_FILE"' EXIT

if DESCRIBE_OUT="$(aws ecs describe-express-gateway-service --region "$AWS_REGION" --service-arn "$SERVICE_ARN" 2>&1)"; then
  echo "Service exists - rolling out image ${IMAGE}"
  jq -n --arg arn "$SERVICE_ARN" --arg exec "$EXECUTION_ROLE" --arg task "$TASK_ROLE" \
    --argjson container "$CONTAINER_JSON" --argjson scaling "$SCALING_JSON" '{
      serviceArn: $arn, executionRoleArn: $exec, taskRoleArn: $task,
      healthCheckPath: "/api/health", cpu: "1024", memory: "2048",
      primaryContainer: $container, scalingTarget: $scaling }' > "$INPUT_FILE"
  aws ecs update-express-gateway-service --region "$AWS_REGION" --cli-input-json "file://$INPUT_FILE" > /dev/null
elif echo "$DESCRIBE_OUT" | grep -qiE "ServiceNotFound|not found|does not exist|MISSING|INACTIVE"; then
  echo "Creating service ${SERVICE_NAME} (first deploy; ECS Express Mode also creates the load balancer, this takes a few minutes)"
  jq -n --arg name "$SERVICE_NAME" --arg exec "$EXECUTION_ROLE" --arg infra "$INFRA_ROLE" --arg task "$TASK_ROLE" \
    --argjson container "$CONTAINER_JSON" --argjson scaling "$SCALING_JSON" '{
      serviceName: $name, executionRoleArn: $exec, infrastructureRoleArn: $infra, taskRoleArn: $task,
      healthCheckPath: "/api/health", cpu: "1024", memory: "2048",
      primaryContainer: $container, scalingTarget: $scaling }' > "$INPUT_FILE"
  aws ecs create-express-gateway-service --region "$AWS_REGION" --cli-input-json "file://$INPUT_FILE" > /dev/null
else
  echo "Could not check the service:" >&2
  echo "$DESCRIBE_OUT" >&2
  exit 1
fi

# Wait for a public URL, then for the app itself to answer.
ENDPOINT=""
for attempt in $(seq 1 60); do
  ENDPOINT="$(aws ecs describe-express-gateway-service --region "$AWS_REGION" --service-arn "$SERVICE_ARN" \
    --query 'service.activeConfigurations[0].ingressPaths[0].endpoint' --output text 2>/dev/null || true)"
  if [ -n "$ENDPOINT" ] && [ "$ENDPOINT" != "None" ]; then break; fi
  echo "Attempt ${attempt}/60: waiting for the service URL..."; sleep 20
done
if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "None" ]; then
  echo "The service has no URL yet. Check ECS -> Clusters -> default -> ${SERVICE_NAME} in the AWS console." >&2
  exit 1
fi
URL="https://${ENDPOINT#https://}"

for attempt in $(seq 1 45); do
  if curl -fsS --max-time 10 "${URL%/}/api/health" > /dev/null 2>&1; then
    echo "Deployed and healthy: ${URL}"
    [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "Meridian AI is live at ${URL}" >> "$GITHUB_STEP_SUMMARY"
    exit 0
  fi
  echo "Attempt ${attempt}/45: app not answering yet..."; sleep 20
done
echo "The service was created but /api/health never answered. Read the logs in CloudWatch: ${LOG_GROUP}" >&2
exit 1
