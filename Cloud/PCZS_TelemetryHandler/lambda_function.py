# Cloud/PCZS_TelemetryHandler/lambda_function.py
import json
import boto3
import decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
telemetry_table = dynamodb.Table('PCZS_Telemetry')

# Global CORS headers
CORS_HEADERS = {
    'Access-Control-Allow-Origin': 'http://pczs-dashboard.s3-website.us-east-2.amazonaws.com',
    'Access-Control-Allow-Credentials': True,
    'Content-Type': 'application/json'
}

# Fix for Decimal serialization
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)

def lambda_handler(event, context):
    print(f"Received event: {event}")
    
    path = event.get('path', '')
    http_method = event.get('httpMethod', '')

    if path == '/telemetry':
        if http_method == 'GET':
            return get_latest_telemetry(event)
        elif http_method == 'POST':
            return store_telemetry(event)

    return {
        'statusCode': 404,
        'headers': CORS_HEADERS,
        'body': json.dumps({'error': 'Not found'})
    }

def get_latest_telemetry(event):
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        workspace_id = query_params.get('workspace_id')
        
        if not workspace_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Missing required parameter: workspace_id'})
            }

        # Query the latest telemetry record for this workspace
        response = telemetry_table.query(
            KeyConditionExpression=Key('workspace_id').eq(workspace_id),
            ScanIndexForward=False,  # Sort in descending order (newest first)
            Limit=1  # Get only the most recent record
        )

        if not response['Items']:
            return {
                'statusCode': 404,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'No telemetry data found for the specified workspace'})
            }

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(response['Items'][0], cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting telemetry: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }

def store_telemetry(event):
    try:
        body = json.loads(event.get('body', '{}'))

        required_fields = ['workspace_id', 'timestamp', 'temperature', 'humidity']
        
        for field in required_fields:
            if field not in body:
                return {
                    'statusCode': 400,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }

        # Store telemetry data in DynamoDB
        telemetry_table.put_item(Item=body)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'success': True, 'message': 'Telemetry data stored'})
        }
    except Exception as e:
        print(f"Error storing telemetry: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }