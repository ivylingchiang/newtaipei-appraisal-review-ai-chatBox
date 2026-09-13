#!/usr/bin/env bash
# 把 output/ 服務重新建置、推上 ECR，並讓 ECS Fargate 換上新映像。
#
# 從專案根目錄執行：
#     ./service/deploy-aws.sh
#
# 首次部署用的 ECR repo／IAM role／cluster／security group 已經建好，
# 這支腳本只負責日常更新（output/ 改過之後重推一次）。
set -euo pipefail

# aws CLI 裝在 ~/.local/bin，但那個目錄不在預設 PATH 上
if [ -x "$HOME/.local/bin/aws" ]; then
  case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) PATH="$HOME/.local/bin:$PATH" ;; esac
fi
command -v aws >/dev/null || { echo "找不到 aws CLI" >&2; exit 1; }

# 憑證先檢查再建置：本專案的金鑰放在 ~/.zshrc（互動式 shell 才載入）且帶 session token，
# 過期是常態。先問一次身分，免得映像建了好幾分鐘才在推送那一步失敗。
if ! ACCOUNT_NOW=$(aws sts get-caller-identity --query Account --output text 2>&1); then
  echo "AWS 憑證無法使用：$ACCOUNT_NOW" >&2
  echo "  ~/.zshrc 的 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN 可能已過期；" >&2
  echo "  更新後請在互動式終端機執行本腳本（非互動 shell 不會載入 ~/.zshrc）。" >&2
  exit 1
fi

ACCOUNT=242971039848
REGION=us-west-2
CLUSTER=ntpc-appraisal
SERVICE=ntpc-appraisal-output
REPO=ntpc-appraisal-output
IMAGE="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com/$REPO:latest"

cd "$(dirname "$0")/.."

if [ "$ACCOUNT_NOW" != "$ACCOUNT" ]; then
  echo "目前登入的帳號是 $ACCOUNT_NOW，本腳本部署的是 $ACCOUNT" >&2
  exit 1
fi

echo "==> 建置映像（Fargate 跑 ARM64，與 Apple Silicon 同架構）"
docker build --platform linux/arm64 -f service/Dockerfile -t "$IMAGE" .

echo "==> 推上 ECR"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
docker push "$IMAGE"

echo "==> 讓 ECS 拉新映像（同一個 task definition，強制重新部署）"
aws ecs update-service --cluster "$CLUSTER" --service "$SERVICE" \
  --force-new-deployment --query 'service.serviceName' --output text
aws ecs wait services-stable --cluster "$CLUSTER" --services "$SERVICE"

echo "==> 取得新的公開 IP（每次換任務都會變）"
TASK=$(aws ecs list-tasks --cluster "$CLUSTER" --service-name "$SERVICE" \
  --query 'taskArns[0]' --output text)
ENI=$(aws ecs describe-tasks --cluster "$CLUSTER" --tasks "$TASK" \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" --output text)
IP=$(aws ec2 describe-network-interfaces --network-interface-ids "$ENI" \
  --query 'NetworkInterfaces[0].Association.PublicIp' --output text)

echo
echo "部署完成： http://$IP:8000/"
