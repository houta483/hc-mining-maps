#!/bin/bash
# Fix ECR permissions for BoreholeAppEC2Role
# Usage: ./scripts/fix-ecr-permissions.sh

set -e

ROLE_NAME="BoreholeAppEC2Role"
REGION="${AWS_REGION:-us-east-2}"
PROFILE="${AWS_PROFILE:-hcmining-prod}"

echo "🔧 Fixing ECR Permissions for IAM Role"
echo "======================================="
echo ""
echo "Role: $ROLE_NAME"
echo "Region: $REGION"
echo ""

# Check if role exists
if ! aws iam get-role --role-name "$ROLE_NAME" --profile "$PROFILE" &>/dev/null; then
    echo "❌ Role $ROLE_NAME not found"
    echo "   Please create the role first or check the name"
    exit 1
fi

echo "✅ Role found"

# Create policy document
POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:DescribeRepositories",
        "ecr:ListImages"
      ],
      "Resource": "arn:aws:ecr:${REGION}:*:repository/*"
    }
  ]
}
EOF
)

POLICY_NAME="BoreholeAppECRPolicy"
POLICY_ARN=""

echo "📝 Creating/Updating IAM policy: $POLICY_NAME"

# Check if policy exists
if aws iam get-policy --policy-arn "arn:aws:iam::553165044639:policy/$POLICY_NAME" --profile "$PROFILE" &>/dev/null; then
    echo "   Policy exists, creating new version..."
    # Create new policy version
    POLICY_VERSION=$(aws iam create-policy-version \
        --policy-arn "arn:aws:iam::553165044639:policy/$POLICY_NAME" \
        --policy-document "$POLICY_DOC" \
        --set-as-default \
        --profile "$PROFILE" \
        --query 'PolicyVersion.VersionId' \
        --output text)
    echo "   ✅ Created policy version: $POLICY_VERSION"
    POLICY_ARN="arn:aws:iam::553165044639:policy/$POLICY_NAME"
else
    echo "   Creating new policy..."
    POLICY_ARN=$(aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --policy-document "$POLICY_DOC" \
        --profile "$PROFILE" \
        --query 'Policy.Arn' \
        --output text)
    echo "   ✅ Created policy: $POLICY_ARN"
fi

echo ""
echo "📎 Attaching policy to role..."

# Check if policy is already attached
ATTACHED=$(aws iam list-attached-role-policies \
    --role-name "$ROLE_NAME" \
    --profile "$PROFILE" \
    --query "AttachedPolicies[?PolicyArn=='$POLICY_ARN'].PolicyArn" \
    --output text)

if [ -z "$ATTACHED" ]; then
    aws iam attach-role-policy \
        --role-name "$ROLE_NAME" \
        --policy-arn "$POLICY_ARN" \
        --profile "$PROFILE"
    echo "   ✅ Attached policy to role"
else
    echo "   ✅ Policy already attached"
fi

echo ""
echo "======================================="
echo "✅ ECR permissions added successfully!"
echo ""
echo "The role now has permissions to:"
echo "  • Get ECR authorization tokens"
echo "  • Pull images from borehole-* repositories"
echo "  • List and describe repositories"
echo ""
echo "🎯 Next step: Run deployment again"
echo "   ./scripts/deploy-ssm.sh"

