#!/usr/bin/env python3
"""
PCZS: Personalized Comfort Zones System - SenseHat Mode
This module handles sensor data collection and publishes to AWS IoT
"""
import time
import json
import datetime
import uuid
from sense_hat import SenseHat
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configuration
THING_NAME = "PCZS"
WORKSPACE_ID = "workspace_1"
ENDPOINT = "a2ao1owrs8g0lu-ats.iot.us-east-2.amazonaws.com"
CLIENT_ID = f"pczs-sensehat-{uuid.uuid4().hex[:8]}"
CERT_PATH = "/home/smartsys/pczs/cert/"
CERT_FILE = CERT_PATH + "certificate.pem.crt"
KEY_FILE = CERT_PATH + "private.pem.key"
ROOT_CA = CERT_PATH + "AmazonRootCA1.pem"
TELEMETRY_TOPIC = f"pczs/{WORKSPACE_ID}/telemetry"
SHADOW_UPDATE_TOPIC = f"$aws/things/{THING_NAME}/shadow/update"
SHADOW_UPDATE_ACCEPTED_TOPIC = f"$aws/things/{THING_NAME}/shadow/update/accepted"
SHADOW_UPDATE_DELTA_TOPIC = f"$aws/things/{THING_NAME}/shadow/update/delta"

# Initialize SenseHat
sense = SenseHat()
sense.clear()

# Colors
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

# State
fan_state = False
comfort_settings = {
    "preferred_temp": 23.0,
    "preferred_humidity": 50.0,
    "temp_threshold": 1.0,
    "humidity_threshold": 10.0,
}

def indicate_comfort_status(temp, humidity):
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    if abs(temp - pref_temp) <= temp_threshold:
        sense.clear(GREEN)  # Comfortable
    elif temp > pref_temp:
        sense.clear(RED)    # Too hot
    else:
        sense.clear(BLUE)   # Too cold

def control_fan(temp):
    global fan_state
    pref_temp = comfort_settings["preferred_temp"]
    temp_threshold = comfort_settings["temp_threshold"]
    
    # Get stored occupancy from shadow (defaulting to True for testing)
    occupied = True
    
    if temp > (pref_temp + temp_threshold) and occupied:
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
    temperature = sense.get_temperature()
    # Adjust temperature reading as SenseHat tends to read high due to CPU heat
    temperature = round(temperature - 8, 1)  # Adjust by approximate offset, round to 1 decimal
    
    humidity = sense.get_humidity()
    humidity = round(humidity, 1)
    
    # Use LED to indicate comfort status
    indicate_comfort_status(temperature, humidity)
    
    # Control fan based on temperature
    fan_on = control_fan(temperature)
    
    timestamp = datetime.datetime.now().isoformat()

    payload = {
        "workspace_id": WORKSPACE_ID,
        "timestamp": timestamp,
        "temperature": temperature,
        "humidity": humidity,
        "fan_state": fan_on
    }

    shadow_payload = {
        "state": {
            "reported": {
                "temperature": temperature,
                "humidity": humidity,
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
    global mqtt_connection

    # Display startup message
    sense.show_message("PCZS", text_colour=(255, 165, 0), scroll_speed=0.05)

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
        print("SenseHat Mode Running. Press Ctrl+C to exit.")
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
    finally:
        print("Disconnecting...")
        sense.clear()
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        print("Cleanup complete")

if __name__ == "__main__":
    main()