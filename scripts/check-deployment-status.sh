#!/bin/bash
# Check deployment status - verify images, server, and deployment readiness

set -e

REGION="${AWS_REGION:-us-east-2}"
PROFILE="${AWS_PROFILE:-hcmining-prod}"
SERVER_IP="${SERVER_IP:-18.216.19.153}"
REPOSITORIES=("borehole-frontend" "borehole-backend" "borehole-pipeline")

echo "🔍 Checking Deployment Status"
echo "=============================="
echo ""

# Check 1: GitHub Actions build status
echo "1️⃣  GitHub Actions Build Status"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   📋 Check manually:"
echo "      https://github.com/houta483/hc-mining-maps/actions"
echo "   Status: ⚠️  Manual check required"
echo ""

# Check 2: ECR Images
echo "2️⃣  ECR Image Availability"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if command -v aws &> /dev/null; then
    ECR_REGISTRY=$(aws ecr describe-registry --region "$REGION" --profile "$PROFILE" 2>/dev/null | jq -r '.registryId' 2>/dev/null || echo "")
    if [ -z "$ECR_REGISTRY" ]; then
        ECR_REGISTRY=$(aws sts get-caller-identity --region "$REGION" --profile "$PROFILE" 2>/dev/null | jq -r '.Account' 2>/dev/null || echo "")
    fi
    
    if [ -n "$ECR_REGISTRY" ]; then
        REGISTRY="${ECR_REGISTRY}.dkr.ecr.${REGION}.amazonaws.com"
        echo "   Registry: $REGISTRY"
        echo ""
        
        for repo in "${REPOSITORIES[@]}"; do
            echo "   📦 $repo:"
            if aws ecr describe-images --repository-name "$repo" --region "$REGION" --profile "$PROFILE" --max-items 1 &>/dev/null; then
                LATEST_TAG=$(aws ecr describe-images --repository-name "$repo" --region "$REGION" --profile "$PROFILE" --query 'sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]' --output text 2>/dev/null || echo "none")
                if [ "$LATEST_TAG" != "none" ] && [ "$LATEST_TAG" != "None" ]; then
                    echo "      ✅ Latest: $LATEST_TAG"
                else
                    echo "      ⚠️  Has images but no tags"
                fi
            else
                echo "      ❌ No images found"
            fi
        done
    else
        echo "   ⚠️  Could not determine ECR registry (check AWS credentials)"
    fi
else
    echo "   ⚠️  AWS CLI not installed - cannot check ECR"
fi
echo ""

# Check 3: Server connectivity
echo "3️⃣  Server Connectivity"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Server: $SERVER_IP"
if ping -c 1 -W 2 "$SERVER_IP" &>/dev/null; then
    echo "   ✅ Server is reachable"
else
    echo "   ⚠️  Server ping failed (may be firewall blocking ICMP)"
fi
echo ""

# Check 4: SSH access
echo "4️⃣  SSH Access"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if timeout 3 ssh -o ConnectTimeout=2 -o StrictHostKeyChecking=no ubuntu@"$SERVER_IP" echo "connected" &>/dev/null 2>&1; then
    echo "   ✅ SSH access works"
    
    # Check if Docker is installed
    DOCKER_CHECK=$(ssh -o ConnectTimeout=2 ubuntu@"$SERVER_IP" "command -v docker" 2>/dev/null || echo "")
    if [ -n "$DOCKER_CHECK" ]; then
        echo "   ✅ Docker installed"
    else
        echo "   ⚠️  Docker not installed (run setup-server.sh)"
    fi
else
    echo "   ⚠️  SSH access failed (try AWS Systems Manager)"
    echo "   Alternative:"
    echo "      aws ssm start-session --target i-03169bf6f17bc4a23 --region $REGION --profile $PROFILE"
fi
echo ""

# Check 5: Services running
echo "5️⃣  Application Services"
echo "   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if timeout 3 curl -s "http://$SERVER_IP" &>/dev/null; then
    echo "   ✅ Frontend responding on port 80"
else
    echo "   ⚠️  Frontend not responding (may not be deployed yet)"
fi

if timeout 3 curl -s "http://$SERVER_IP/api/health" &>/dev/null; then
    echo "   ✅ Backend API responding"
else
    echo "   ⚠️  Backend API not responding"
fi
echo ""

# Summary
echo "📊 DEPLOYMENT STATUS SUMMARY"
echo "=============================="
echo ""
echo "✅ Ready to deploy if:"
echo "   1. GitHub Actions build completed successfully"
echo "   2. ECR images are available (see above)"
echo "   3. Server is accessible (see above)"
echo ""
echo "🚀 Next Steps:"
echo ""
if command -v aws &> /dev/null && aws sts get-caller-identity --profile "$PROFILE" &>/dev/null 2>&1; then
    echo "   1. Verify build completed: https://github.com/houta483/hc-mining-maps/actions"
    echo "   2. Deploy:"
    echo "      ./scripts/deploy-prod.sh $SERVER_IP ubuntu"
    echo ""
    echo "   3. Or use Systems Manager if SSH fails:"
    echo "      aws ssm start-session --target i-03169bf6f17bc4a23 --region $REGION --profile $PROFILE"
else
    echo "   ⚠️  AWS credentials not configured"
    echo "   Set up AWS profile:"
    echo "      export AWS_PROFILE=$PROFILE"
    echo "      aws configure --profile $PROFILE"
fi
echo ""

