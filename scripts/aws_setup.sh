#!/bin/bash
# aws_setup.sh
# Automated setup script for PCZS AWS resources

echo "Setting up PCZS AWS Infrastructure..."

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "AWS CLI not found. Please install it first."
    exit 1
fi

# Check AWS credentials
aws sts get-caller-identity > /dev/null
if [ $? -ne 0 ]; then
    echo "AWS credentials not set up. Please run 'aws configure' first."
    exit 1
fi

# Set variables
THING_NAME="PCZS"
REGION="us-east-2"
POLICY_NAME="PCZS_Policy"
CERT_PATH="./cert"

# Create IoT Thing
echo "Creating IoT Thing: $THING_NAME"
aws iot create-thing --thing-name $THING_NAME --region $REGION

# Create IoT Policy
echo "Creating IoT Policy: $POLICY_NAME"
aws iot create-policy --policy-name $POLICY_NAME --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"iot:*","Resource":"*"}]}' --region $REGION

# Create certificate and attach policy
echo "Creating certificate and attaching policy"
mkdir -p $CERT_PATH
CERT_RESULT=$(aws iot create-keys-and-certificate --set-as-active --certificate-pem-outfile "$CERT_PATH/certificate.pem.crt" --private-key-outfile "$CERT_PATH/private.pem.key" --region $REGION)
CERT_ARN=$(echo $CERT_RESULT | jq -r '.certificateArn')

# Attach policy to certificate
aws iot attach-policy --policy-name $POLICY_NAME --target $CERT_ARN --region $REGION

# Attach certificate to thing
aws iot attach-thing-principal --thing-name $THING_NAME --principal $CERT_ARN --region $REGION

# Download CA certificate
curl -o $CERT_PATH/AmazonRootCA1.pem https://www.amazontrust.com/repository/AmazonRootCA1.pem

# Create DynamoDB tables
echo "Creating DynamoDB tables"
aws dynamodb create-table \
    --table-name PCZS_Telemetry \
    --attribute-definitions \
        AttributeName=workspace_id,AttributeType=S \
        AttributeName=timestamp,AttributeType=S \
    --key-schema \
        AttributeName=workspace_id,KeyType=HASH \
        AttributeName=timestamp,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region $REGION

aws dynamodb create-table \
    --table-name PCZS_UserPreferences \
    --attribute-definitions \
        AttributeName=user_id,AttributeType=S \
        AttributeName=workspace_id,AttributeType=S \
    --key-schema \
        AttributeName=user_id,KeyType=HASH \
        AttributeName=workspace_id,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region $REGION

# Create IoT rule for storing data in DynamoDB
echo "Creating IoT rule for DynamoDB"
aws iot create-topic-rule \
    --rule-name PCZS_DynamoDB_Rule \
    --topic-rule-payload '{"sql":"SELECT * FROM '"'pczs/+/telemetry'"'","actions":[{"dynamoDBv2":{"roleArn":"arn:aws:iam::ACCOUNT_ID:role/PCZS_DynamoDB_Role","putItem":{"tableName":"PCZS_Telemetry"}}}],"ruleDisabled":false}' \
    --region $REGION

echo "AWS Setup completed successfully!"
echo "Note: You'll need to manually create a Lambda function and API Gateway for the web interface."