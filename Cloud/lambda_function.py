# Cloud/lambda_function.py
import json
import boto3
import datetime
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')
preferences_table = dynamodb.Table('PCZS_UserPreferences')
telemetry_table = dynamodb.Table('PCZS_Telemetry')

def lambda_handler(event, context):
    """
    Lambda handler for PCZS API Gateway
    Handles preferences and telemetry data for the Personalized Comfort Zones System
    """
    print(f"Received event: {event}")
    
    # Extract path and HTTP method
    path = event.get('path', '')
    http_method = event.get('httpMethod', '')
    
    # Route the request based on path and method
    if path == '/preferences':
        if http_method == 'GET':
            return get_preferences(event)
        elif http_method == 'POST':
            return save_preferences(event)
    elif path == '/telemetry':
        if http_method == 'GET':
            return get_telemetry(event)
    
    # Default response for unsupported paths
    return {
        'statusCode': 404,
        'headers': {'Content-Type': 'application/json'},
        'body': json.dumps({'error': 'Not found'})
    }

def get_preferences(event):
    """Get user preferences from DynamoDB"""
    try:
        # Extract query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        user_id = query_params.get('user_id')
        workspace_id = query_params.get('workspace_id')
        
        if not user_id or not workspace_id:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Missing required parameters: user_id and workspace_id'})
            }
        
        # Query DynamoDB
        response = preferences_table.get_item(
            Key={
                'user_id': user_id,
                'workspace_id': workspace_id
            }
        )
        
        # Check if item was found
        if 'Item' not in response:
            # Return default preferences
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
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps(default_preferences)
            }
        
        # Return the preferences
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(response['Item'])
        }
    except Exception as e:
        print(f"Error getting preferences: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def save_preferences(event):
    """Save user preferences to DynamoDB"""
    try:
        # Parse request body
        body = json.loads(event.get('body', '{}'))
        
        # Required fields
        required_fields = ['user_id', 'workspace_id', 'preferred_temp', 'temp_threshold', 
                          'preferred_humidity', 'humidity_threshold']
        
        # Check all required fields are present
        for field in required_fields:
            if field not in body:
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'error': f'Missing required field: {field}'})
                }
        
        # Add timestamp
        body['timestamp'] = datetime.datetime.now().isoformat()
        
        # Save to DynamoDB
        preferences_table.put_item(Item=body)
        
        # Also update device shadow
        update_device_shadow(body)
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'success': True, 'message': 'Preferences saved'})
        }
    except Exception as e:
        print(f"Error saving preferences: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def get_telemetry(event):
    """Get latest telemetry data from DynamoDB"""
    try:
        # Extract query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        workspace_id = query_params.get('workspace_id')
        
        if not workspace_id:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Missing required parameter: workspace_id'})
            }
        
        # Query DynamoDB for latest telemetry
        response = telemetry_table.query(
            KeyConditionExpression=Key('workspace_id').eq(workspace_id),
            ScanIndexForward=False,  # descending order (newest first)
            Limit=1
        )
        
        # Check if items were found
        if not response['Items']:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'No telemetry data found for the specified workspace'})
            }
        
        # Return the latest telemetry data
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(response['Items'][0])
        }
    except Exception as e:
        print(f"Error getting telemetry: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def update_device_shadow(preferences):
    """Update the device shadow with new comfort settings"""
    try:
        # Initialize IoT client
        iot_client = boto3.client('iot-data')
        
        # Extract comfort settings
        comfort_settings = {
            'preferred_temp': preferences['preferred_temp'],
            'temp_threshold': preferences['temp_threshold'],
            'preferred_humidity': preferences['preferred_humidity'],
            'humidity_threshold': preferences['humidity_threshold']
        }
        
        # Create shadow document update
        shadow_payload = {
            'state': {
                'desired': comfort_settings
            }
        }
        
        # Update shadow
        iot_client.update_thing_shadow(
            thingName='PCZS',
            payload=json.dumps(shadow_payload)
        )
        print(f"Updated device shadow with new comfort settings: {comfort_settings}")
    except Exception as e:
        print(f"Error updating device shadow: {e}")
        # We don't want to fail the API call if only the shadow update fails
        # So we just log the error and continue