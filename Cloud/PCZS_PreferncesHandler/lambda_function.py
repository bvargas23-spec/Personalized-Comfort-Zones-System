# Cloud/lambda_function.py
import json
import boto3
import datetime
import decimal
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
preferences_table = dynamodb.Table('PCZS_UserPreferences')
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

    if path == '/preferences':
        if http_method == 'GET':
            return get_preferences(event)
        elif http_method == 'POST':
            return save_preferences(event)
    elif path == '/telemetry':
        if http_method == 'GET':
            return get_telemetry(event)

    return {
        'statusCode': 404,
        'headers': CORS_HEADERS,
        'body': json.dumps({'error': 'Not found'})
    }

def get_preferences(event):
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        user_id = query_params.get('user_id')
        workspace_id = query_params.get('workspace_id')
        
        if not user_id or not workspace_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Missing required parameters: user_id and workspace_id'})
            }
        
        response = preferences_table.get_item(
            Key={
                'user_id': user_id,
                'workspace_id': workspace_id
            }
        )
        
        if 'Item' not in response:
            default_preferences = {
                'user_id': user_id,
                'workspace_id': workspace_id,
                'preferred_temp': 23.0,
                'temp_threshold': 1.0,
                'preferred_humidity': 50,
                'humidity_threshold': 10
            }
            return {
                'statusCode': 200,
                'headers': CORS_HEADERS,
                'body': json.dumps(default_preferences)
            }
        
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps(response['Item'], cls=DecimalEncoder)
        }
    except Exception as e:
        print(f"Error getting preferences: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }

def save_preferences(event):
    try:
        body = json.loads(event.get('body', '{}'))

        required_fields = ['user_id', 'workspace_id', 'preferred_temp', 'temp_threshold',
                           'preferred_humidity', 'humidity_threshold']
        
        for field in required_fields:
            if field not in body:
                return {
                    'statusCode': 400,
                    'headers': CORS_HEADERS,
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }

        body['timestamp'] = datetime.datetime.now().isoformat()
        preferences_table.put_item(Item=body)
        update_device_shadow(body)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({'success': True, 'message': 'Preferences saved'})
        }
    except Exception as e:
        print(f"Error saving preferences: {e}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }

def get_telemetry(event):
    try:
        query_params = event.get('queryStringParameters', {}) or {}
        workspace_id = query_params.get('workspace_id')
        
        if not workspace_id:
            return {
                'statusCode': 400,
                'headers': CORS_HEADERS,
                'body': json.dumps({'error': 'Missing required parameter: workspace_id'})
            }

        response = telemetry_table.query(
            KeyConditionExpression=Key('workspace_id').eq(workspace_id),
            ScanIndexForward=False,
            Limit=1
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

def update_device_shadow(preferences):
    try:
        iot_client = boto3.client('iot-data')

        comfort_settings = {
            'preferred_temp': preferences['preferred_temp'],
            'temp_threshold': preferences['temp_threshold'],
            'preferred_humidity': preferences['preferred_humidity'],
            'humidity_threshold': preferences['humidity_threshold']
        }

        shadow_payload = {
            'state': {
                'desired': comfort_settings
            }
        }

        iot_client.update_thing_shadow(
            thingName='PCZS',
            payload=json.dumps(shadow_payload)
        )
        print(f"Updated device shadow with new comfort settings: {comfort_settings}")
    except Exception as e:
        print(f"Error updating device shadow: {e}")
