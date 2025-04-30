#!/usr/bin/env python3
"""
PCZS: Personalized Comfort Zones System - Integrated Sensor Script
Handles SenseHat, PIR, and DHT22 sensors and publishes to AWS IoT
"""
import time
import json
import datetime
import uuid
import RPi.GPIO as GPIO
import traceback
try:
    import board
    import adafruit_dht
    DHT_AVAILABLE = True
except ImportError:
    print("Warning: adafruit_dht module not available, will use SenseHat only")
    DHT_AVAILABLE = False
from sense_hat import SenseHat
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
import boto3
from botocore.exceptions import ClientError

# Configuration
THING_NAME = "PCZS"
WORKSPACE_ID = "workspace_1"
ENDPOINT = "a2ao1owrs8g0lu-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = f"pczs-integrated-{uuid.uuid4().hex[:8]}"
CERT_PATH = "/home/smartsys/pczs/cert/"
CERT_FILE = CERT_PATH + "certificate.pem.crt"
KEY_FILE = CERT_PATH + "private.pem.key"
ROOT_CA = CERT_PATH + "AmazonRootCA1.pem"
TELEMETRY_TOPIC = f"pczs/{WORKSPACE_ID}/telemetry"
SHADOW_UPDATE_TOPIC = f"$aws/things/{THING_NAME}/shadow/update"
SHADOW_UPDATE_ACCEPTED_TOPIC = f"$aws/things/{THING_NAME}/shadow/update/accepted"
SHADOW_UPDATE_DELTA_TOPIC = f"$aws/things/{THING_NAME}/shadow/update/delta"

# GPIO Pins
PIR_PIN = 17
DHT_PIN = 4  # GPIO4 for DHT22

# Initialize SenseHat
sense = SenseHat()
sense.clear()

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

# Initialize DHT22 sensor
if DHT_AVAILABLE:
    try:
        dht_sensor = adafruit_dht.DHT22(board.D4)
        print("DHT22 sensor initialized")
    except Exception as e:
        print(f"Warning: Could not initialize DHT22: {e}")
        dht_sensor = None
else:
    dht_sensor = None

# Colors
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)

# State
fan_state = False
occupancy = False
last_motion_time = 0
OCCUPANCY_TIMEOUT = 300  # seconds

comfort_settings = {
    "preferred_temp": 23.0,
    "preferred_humidity": 50.0,
    "temp_threshold": 1.0,
    "humidity_threshold": 10.0,
}

def get_user_preferences(user_id, workspace_id):
    """Retrieves user preferences from DynamoDB"""
    try:
        dynamodb = boto3.resource('dynamodb', region_name='us-east-2')
        table = dynamodb.Table('PCZS_UserPreferences')
        response = table.get_item(
            Key={
                'user_id': user_id,
                'workspace_id': workspace_id
            }
        )
        if 'Item' in response:
            prefs = response['Item']
            print(f"Retrieved preferences: {prefs}")
            return prefs
        else:
            print("No preferences found, using defaults")
            return comfort_settings  # Use existing defaults
    except ClientError as e:
        print(f"Error retrieving preferences: {e}")
        return comfort_settings  # Use existing defaults
    except Exception as e:
        print(f"Unexpected error accessing DynamoDB: {e}")
        traceback.print_exc()
        return comfort_settings  # Use existing defaults

def detect_occupancy():
    """Detect motion using PIR sensor and update occupancy state"""
    global occupancy, last_motion_time
    motion = GPIO.input(PIR_PIN)
    if motion:
        print("Motion detected!")
        occupancy = True
        last_motion_time = time.time()
        # Visual indicator for occupancy
        sense.show_letter("O", GREEN)
        time.sleep(0.5)
        sense.clear()
    elif time.time() - last_motion_time > OCCUPANCY_TIMEOUT:
        print("No motion detected — workspace unoccupied")
        occupancy = False
    return occupancy

def read_dht22():
    """Read temperature and humidity from DHT22 sensor"""
    if not DHT_AVAILABLE or dht_sensor is None:
        # Fallback to SenseHat values if DHT22 is not available
        return None, None
    
    try:
        temperature = dht_sensor.temperature
        humidity = dht_sensor.humidity
        if humidity is not None and temperature is not None:
            humidity = round(humidity, 1)
            temperature = round(temperature, 1)
            print(f"DHT22: Temp={temperature}°C, Humidity={humidity}%")
            return temperature, humidity
    except RuntimeError as e:
        # DHT22 sensors can occasionally fail to read
        print(f"DHT22 reading error: {e}")
    except Exception as e:
        print(f"Unexpected DHT22 error: {e}")
    
    return None, None

def indicate_comfort_status(temp, humidity):
    """Display comfort status on SenseHat LED matrix"""
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    
    # Only show comfort status when workspace is occupied
    if not occupancy:
        sense.clear()  # Turn off display when unoccupied
        return
        
    if abs(temp - pref_temp) <= temp_threshold:
        sense.clear(GREEN)  # Comfortable
    elif temp > pref_temp:
        sense.clear(RED)    # Too hot
    else:
        sense.clear(BLUE)   # Too cold

def control_fan(temp):
    """Control fan based on temperature and occupancy"""
    global fan_state
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    
    # Only control fan when workspace is occupied
    if not occupancy:
        if fan_state:
            print("Fan control: Turning fan OFF (unoccupied)")
            fan_state = False
        return fan_state
    
    if temp > (pref_temp + temp_threshold):
        if not fan_state:
            print("Fan control: Turning fan ON")
            # Visual indicator for fan state
            sense.show_letter("F", GREEN)
            time.sleep(0.5)
            sense.clear()
            fan_state = True
    else:
        if fan_state:
            print("Fan control: Turning fan OFF")
            sense.show_letter("O", BLUE)
            time.sleep(0.5)
            sense.clear()
            fan_state = False
    return fan_state

def read_sensors():
    """Read all sensors and prepare payload for MQTT publishing"""
    # Check occupancy first
    is_occupied = detect_occupancy()
    
    # Read DHT22 sensor (more accurate than SenseHat for temperature/humidity)
    dht_temp, dht_humidity = read_dht22()
    
    # Read SenseHat sensors as backup
    sh_temp = sense.get_temperature()
    sh_humidity = sense.get_humidity()
    
    # Use DHT22 readings if available, otherwise fall back to SenseHat
    temperature = dht_temp if dht_temp is not None else sh_temp - 8  # Adjust SenseHat temp
    humidity = dht_humidity if dht_humidity is not None else sh_humidity
    
    # Round values
    temperature = round(temperature, 1)
    humidity = round(humidity, 1)
    
    # Use LED to indicate comfort status
    indicate_comfort_status(temperature, humidity)
    
    # Control fan based on temperature and occupancy
    fan_on = control_fan(temperature)
    
    # Timestamp for telemetry
    timestamp = datetime.datetime.now().isoformat()

    # Create payload for MQTT telemetry
    payload = {
        "workspace_id": WORKSPACE_ID,
        "timestamp": timestamp,
        "temperature": temperature,
        "humidity": humidity,
        "occupied": is_occupied,
        "fan_state": fan_on
    }

    # Create payload for device shadow
    shadow_payload = {
        "state": {
            "reported": {
                "temperature": temperature,
                "humidity": humidity,
                "occupied": is_occupied,
                "fan_state": fan_on
            }
        }
    }

    return payload, shadow_payload

# Callback when connection is accidentally lost.
def on_connection_interrupted(connection, error, **kwargs):
    print(f"Connection interrupted: {error}")

# Callback when an interrupted connection is re-established.
def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print(f"Connection resumed: {return_code}, session_present: {session_present}")

# Callback when a message is received on shadow delta topic
def on_shadow_delta(topic, payload, dup, qos, retain, **kwargs):
    global comfort_settings
    payload_str = payload.decode('utf-8')
    print(f"Received delta message: {payload_str}")
    try:
        delta = json.loads(payload_str).get("state", {})
        # Update only the keys that exist in comfort_settings
        comfort_settings.update({k: delta[k] for k in comfort_settings.keys() if k in delta})
        print(f"Updated comfort settings: {comfort_settings}")
        
        # Display confirmation on SenseHat
        sense.show_message("Updated", text_colour=GREEN, scroll_speed=0.05)
        
        # Update the reported state to match the desired state
        update = {"state": {"reported": comfort_settings}}
        mqtt_connection.publish(
            topic=SHADOW_UPDATE_TOPIC,
            payload=json.dumps(update),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
    except Exception as e:
        print(f"Error handling delta: {e}")
        sense.show_message("Error", text_colour=RED, scroll_speed=0.05)

# Callback when a message is received on shadow accepted topic
def on_shadow_accepted(topic, payload, dup, qos, retain, **kwargs):
    payload_str = payload.decode('utf-8')
    print(f"Shadow update accepted: {payload_str}")

def main():
    global mqtt_connection, comfort_settings

    # Display startup message
    sense.show_message("PCZS", text_colour=ORANGE, scroll_speed=0.05)

    try:
        # Spin up resources
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)

        # Initialize MQTT connection
        mqtt_connection = mqtt_connection_builder.mtls_from_path(
            endpoint=ENDPOINT,
            cert_filepath=CERT_FILE,
            pri_key_filepath=KEY_FILE,
            ca_filepath=ROOT_CA,
            client_bootstrap=client_bootstrap,
            client_id=CLIENT_ID,
            clean_session=True,
            keep_alive_secs=30
        )

        # Connect to AWS IoT Core
        print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
        connect_future = mqtt_connection.connect()
        connect_future.result()
        print("Connected to AWS IoT!")

        # Retrieve user preferences from DynamoDB
        user_id = "user_1"  # This would come from user authentication in a real app
        try:
            retrieved_settings = get_user_preferences(user_id, WORKSPACE_ID)
            if retrieved_settings != comfort_settings:
                comfort_settings.update(retrieved_settings)
                print(f"Applied user preferences: {comfort_settings}")
        except Exception as e:
            print(f"Error retrieving preferences, using defaults: {e}")
            traceback.print_exc()

        # Subscribe to shadow delta and accepted topics
        print(f"Subscribing to {SHADOW_UPDATE_DELTA_TOPIC}...")
        delta_subscribe_future, _ = mqtt_connection.subscribe(
            topic=SHADOW_UPDATE_DELTA_TOPIC,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_shadow_delta
        )
        delta_subscribe_future.result()
        
        print(f"Subscribing to {SHADOW_UPDATE_ACCEPTED_TOPIC}...")
        accepted_subscribe_future, _ = mqtt_connection.subscribe(
            topic=SHADOW_UPDATE_ACCEPTED_TOPIC,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_shadow_accepted
        )
        accepted_subscribe_future.result()
        
        # Report initial comfort settings to shadow
        print("Publishing initial comfort settings...")
        mqtt_connection.publish(
            topic=SHADOW_UPDATE_TOPIC,
            payload=json.dumps({"state": {"reported": comfort_settings}}),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )

        # Main loop
        print("Integrated Sensors Mode Running. Press Ctrl+C to exit.")
        while True:
            telemetry, shadow = read_sensors()
            
            # Publish telemetry data
            mqtt_connection.publish(
                topic=TELEMETRY_TOPIC,
                payload=json.dumps(telemetry),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            # Update device shadow
            mqtt_connection.publish(
                topic=SHADOW_UPDATE_TOPIC,
                payload=json.dumps(shadow),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            print(f"Published telemetry: {telemetry}")
            
            # Check for motion more frequently, but don't flood AWS with messages
            for i in range(5):  # Check every 2 seconds for motion, but publish only every 10 seconds
                if i > 0:  # Skip the first iteration since we just checked
                    detect_occupancy()  # Just check occupancy without publishing
                time.sleep(2)
                
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
    finally:
        print("Disconnecting...")
        if DHT_AVAILABLE and dht_sensor is not None:
            try:
                dht_sensor.exit()
            except:
                pass
        sense.clear()
        try:
            disconnect_future = mqtt_connection.disconnect()
            disconnect_future.result()
        except:
            pass
        GPIO.cleanup()
        print("Cleanup complete")

if __name__ == "__main__":
    main()