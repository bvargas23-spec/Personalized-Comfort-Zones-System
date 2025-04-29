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
import Adafruit_DHT  # You'll need to install this library: pip install Adafruit_DHT
from sense_hat import SenseHat
from awscrt import io, mqtt
from awsiot import mqtt_connection_builder

# Configuration
THING_NAME = "PCZS"
WORKSPACE_ID = "workspace_1"
ENDPOINT = "a2ao1owrs8g0lu-ats.iot.us-east-2.amazonaws.com"  # Use your endpoint
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
YELLOW = (255, 255, 0)

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

def detect_occupancy():
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
    global mqtt_connection

    # Display startup message
    sense.show_message("PCZS", text_colour=(255, 165, 0), scroll_speed=0.05)

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
    finally:
        print("Disconnecting...")
        sense.clear()
        disconnect_future = mqtt_connection.disconnect()
        disconnect_future.result()
        GPIO.cleanup()
        print("Cleanup complete")

if __name__ == "__main__":
    main()