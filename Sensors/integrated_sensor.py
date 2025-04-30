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
import Adafruit_DHT
import boto3
from botocore.exceptions import ClientError
# Fix: Disable IMU check to prevent "Unknown platform" error
import os
os.environ['SENSE_HAT_NO_IMU'] = '1'
from sense_hat import SenseHat
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder
   
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
DHT_PIN = 4
DHT_SENSOR = Adafruit_DHT.DHT22

# Initialize SenseHat
sense = SenseHat()
sense.clear()

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

# Colors
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

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

def detect_occupancy():
    global occupancy, last_motion_time
    motion = GPIO.input(PIR_PIN)
    if motion:
        print("Motion detected!")
        occupancy = True
        last_motion_time = time.time()
        sense.show_letter("O", GREEN)
        time.sleep(0.5)
        sense.clear()
    elif time.time() - last_motion_time > OCCUPANCY_TIMEOUT:
        print("No motion detected — workspace unoccupied")
        occupancy = False
    return occupancy

def read_dht22():
    humidity, temperature = Adafruit_DHT.read_retry(DHT_SENSOR, DHT_PIN)
    if humidity is not None and temperature is not None:
        humidity = round(humidity, 1)
        temperature = round(temperature, 1)
        print(f"DHT22: Temp={temperature}°C, Humidity={humidity}%")
    else:
        print("Failed to get DHT22 reading. Using default values.")
        temperature = 23.0
        humidity = 45.0
    return temperature, humidity

def indicate_comfort_status(temp, humidity):
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    if not occupancy:
        sense.clear()
        return
    if abs(temp - pref_temp) <= temp_threshold:
        sense.clear(GREEN)
    elif temp > pref_temp:
        sense.clear(RED)
    else:
        sense.clear(BLUE)

def control_fan(temp):
    global fan_state
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    if not occupancy:
        if fan_state:
            print("Fan control: Turning fan OFF (unoccupied)")
            fan_state = False
        return fan_state
    if temp > (pref_temp + temp_threshold):
        if not fan_state:
            print("Fan control: Turning fan ON")
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
    is_occupied = detect_occupancy()
    dht_temp, dht_humidity = read_dht22()
    sh_temp = sense.get_temperature()
    sh_humidity = sense.get_humidity()
    temperature = dht_temp if dht_temp is not None else sh_temp - 8
    humidity = dht_humidity if dht_humidity is not None else sh_humidity
    temperature = round(temperature, 1)
    humidity = round(humidity, 1)
    indicate_comfort_status(temperature, humidity)
    fan_on = control_fan(temperature)
    timestamp = datetime.datetime.now().isoformat()
    payload = {
        "workspace_id": WORKSPACE_ID,
        "timestamp": timestamp,
        "temperature": temperature,
        "humidity": humidity,
        "occupied": is_occupied,
        "fan_state": fan_on
    }
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

def on_connection_interrupted(connection, error, **kwargs):
    print(f"Connection interrupted: {error}")

def on_connection_resumed(connection, return_code, session_present, **kwargs):
    print(f"Connection resumed: {return_code}, session_present: {session_present}")

def on_shadow_delta(topic, payload, dup, qos, retain, **kwargs):
    global comfort_settings
    payload_str = payload.decode('utf-8')
    print(f"Received delta message: {payload_str}")
    try:
        delta = json.loads(payload_str).get("state", {})
        comfort_settings.update({k: delta[k] for k in comfort_settings.keys() if k in delta})
        print(f"Updated comfort settings: {comfort_settings}")
        sense.show_message("Updated", text_colour=GREEN, scroll_speed=0.05)
        update = {"state": {"reported": comfort_settings}}
        mqtt_connection.publish(
            topic=SHADOW_UPDATE_TOPIC,
            payload=json.dumps(update),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
    except Exception as e:
        print(f"Error handling delta: {e}")
        sense.show_message("Error", text_colour=RED, scroll_speed=0.05)

def on_shadow_accepted(topic, payload, dup, qos, retain, **kwargs):
    payload_str = payload.decode('utf-8')
    print(f"Shadow update accepted: {payload_str}")

def main():
    global mqtt_connection
    sense.show_message("PCZS", text_colour=(255, 165, 0), scroll_speed=0.05)
    try:
        event_loop_group = io.EventLoopGroup(1)
        host_resolver = io.DefaultHostResolver(event_loop_group)
        client_bootstrap = io.ClientBootstrap(event_loop_group, host_resolver)
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
        print(f"Connecting to {ENDPOINT} with client ID '{CLIENT_ID}'...")
        connect_future = mqtt_connection.connect()
        connect_future.result()
        print("Connected to AWS IoT!")

        print(f"Subscribing to {SHADOW_UPDATE_DELTA_TOPIC}...")
        mqtt_connection.subscribe(
            topic=SHADOW_UPDATE_DELTA_TOPIC,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_shadow_delta
        )

        print(f"Subscribing to {SHADOW_UPDATE_ACCEPTED_TOPIC}...")
        mqtt_connection.subscribe(
            topic=SHADOW_UPDATE_ACCEPTED_TOPIC,
            qos=mqtt.QoS.AT_LEAST_ONCE,
            callback=on_shadow_accepted
        )

        print("Publishing initial comfort settings...")
        mqtt_connection.publish(
            topic=SHADOW_UPDATE_TOPIC,
            payload=json.dumps({"state": {"reported": comfort_settings}}),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )

        print("Integrated Sensors Mode Running. Press Ctrl+C to exit.")
        while True:
            telemetry, shadow = read_sensors()
            mqtt_connection.publish(
                topic=TELEMETRY_TOPIC,
                payload=json.dumps(telemetry),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            mqtt_connection.publish(
                topic=SHADOW_UPDATE_TOPIC,
                payload=json.dumps(shadow),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            print(f"Published telemetry: {telemetry}")
            for i in range(5):
                if i > 0:
                    detect_occupancy()
                time.sleep(2)

    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Disconnecting...")
        sense.clear()
        mqtt_connection.disconnect().result()
        GPIO.cleanup()
        print("Cleanup complete")

if __name__ == "__main__":
    main()
user_id = "user_1"  # This would come from user authentication in a real app
retrieved_settings = get_user_preferences(user_id, WORKSPACE_ID)
comfort_settings.update(retrieved_settings)  # Update with any stored preferences