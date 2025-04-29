#!/usr/bin/env python3
"""
PCZS: Personalized Comfort Zones System - PIR Sensor Mode
This module handles occupancy detection and publishes to AWS IoT
"""
import time
import json
import datetime
import uuid
import RPi.GPIO as GPIO
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configuration
THING_NAME = "PCZS"
WORKSPACE_ID = "workspace_1"
ENDPOINT = "a2ao1owrs8g0lu-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = f"pczs-pir-{uuid.uuid4().hex[:8]}"
CERT_PATH = "/home/smartsys/pczs/cert/"
CERT_FILE = CERT_PATH + "certificate.pem.crt"
KEY_FILE = CERT_PATH + "private.pem.key"
ROOT_CA = CERT_PATH + "AmazonRootCA1.pem"
TELEMETRY_TOPIC = f"pczs/{WORKSPACE_ID}/telemetry"
SHADOW_UPDATE_TOPIC = f"$aws/things/{THING_NAME}/shadow/update"

# GPIO Pins
PIR_PIN = 17

# Initialize GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(PIR_PIN, GPIO.IN)

# State
occupancy = False
last_motion_time = 0
OCCUPANCY_TIMEOUT = 300  # seconds

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
    # Using mock data for environmental sensors
    temperature = 23.5
    humidity = 45.0
    is_occupied = detect_occupancy()
    timestamp = datetime.datetime.now().isoformat()

    payload = {
        "workspace_id": WORKSPACE_ID,
        "timestamp": timestamp,
        "temperature": temperature,
        "humidity": humidity,
        "occupied": is_occupied,
        "fan_state": False
    }

    shadow_payload = {
        "state": {
            "reported": {
                "occupied": is_occupied
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

def main():
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

    # Main loop
    try:
        print("PIR Sensor Mode Running. Press Ctrl+C to exit.")
        while True:
            telemetry, shadow = read_sensors()
            
            # Publish telemetry data
            mqtt_connection.publish(
                topic=TELEMETRY_TOPIC,
                payload=json.dumps(telemetry),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            # Update device shadow with occupancy
            mqtt_connection.publish(
                topic=SHADOW_UPDATE_TOPIC,
                payload=json.dumps(shadow),
                qos=mqtt.QoS.AT_LEAST_ONCE
            )
            
            print(f"Published telemetry: {telemetry}")
            time.sleep(5)  # Check more frequently for motion
    except KeyboardInterrupt:
        print("Exiting...")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Disconnecting...")
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        GPIO.cleanup()
        print("Cleanup complete")

if __name__ == "__main__":
    main()