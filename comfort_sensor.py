#!/usr/bin/env python3
"""
PCZS: Personalized Comfort Zones System
This module handles sensor data collection and publishes to AWS IoT
"""
import time
import json
import datetime
import uuid
import RPi.GPIO as GPIO
import traceback
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configuration
THING_NAME = "PCZS"
WORKSPACE_ID = "workspace_1"
ENDPOINT = "a2ao1owrs8g0lu-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = f"pczs-{WORKSPACE_ID}-{uuid.uuid4().hex[:8]}"
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
LED_R = 22
LED_G = 23
LED_B = 24

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(LED_R, GPIO.OUT)
GPIO.setup(LED_G, GPIO.OUT)
GPIO.setup(LED_B, GPIO.OUT)

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

def set_led_color(r, g, b):
    GPIO.output(LED_R, r)
    GPIO.output(LED_G, g)
    GPIO.output(LED_B, b)

def indicate_comfort_status(temp, humidity):
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    if abs(temp - pref_temp) <= temp_threshold:
        set_led_color(0, 1, 0)  # GREEN
    elif temp > pref_temp:
        set_led_color(1, 0, 0)  # RED
    else:
        set_led_color(0, 0, 1)  # BLUE

def control_fan(temp):
    global fan_state
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    if temp > (pref_temp + temp_threshold) and occupancy:
        if not fan_state:
            print("Turning fan ON")
            fan_state = True
    else:
        if fan_state:
            print("Turning fan OFF")
            fan_state = False
    return fan_state

def detect_occupancy():
    global occupancy, last_motion_time
    motion = GPIO.input(PIR_PIN)
    if motion:
        print("Motion detected!")
        occupancy = True
        last_motion_time = time.time()
    elif time.time() - last_motion_time > OCCUPANCY_TIMEOUT:
        print("No motion detected — workspace unoccupied")
        occupancy = False
    return occupancy

def read_sensors():
    # Using mock data since hardware is broken
    temperature = 23.5
    humidity = 45.0
    is_occupied = detect_occupancy()
    fan_on = control_fan(temperature)
    indicate_comfort_status(temperature, humidity)
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
        update = {"state": {"reported": comfort_settings}}
        mqtt_connection.publish(
            topic=SHADOW_UPDATE_TOPIC,
            payload=json.dumps(update),
            qos=mqtt.QoS.AT_LEAST_ONCE
        )
    except Exception as e:
        print(f"Error handling delta: {e}")
        traceback.print_exc()

# Callback when a message is received on shadow accepted topic
def on_shadow_accepted(topic, payload, dup, qos, retain, **kwargs):
    print(f"Shadow update accepted: {payload.decode('utf-8')}")

def main():
    global mqtt_connection

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
    try:
        print("PCZS system running. Press Ctrl+C to exit.")
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
            time.sleep(10)
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
    finally:
        print("Disconnecting...")
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        GPIO.cleanup()
        print("Cleanup complete")

if __name__ == "__main__":
    main()