# Personalized Comfort Zones System (PCZS)

A smart IoT system that creates individualized thermal comfort zones for workspaces while optimizing energy usage.

## Overview

The Personalized Comfort Zones System (PCZS) addresses the "one-size-fits-all" problem in traditional HVAC systems by allowing individual users to set and maintain their preferred comfort settings at the workspace level. The system uses a combination of sensors, cloud connectivity, and actuators to create personal comfort zones that adapt to user preferences and occupancy.

## Features

- **Personalized comfort settings**: Users can set their preferred temperature and humidity levels
- **Occupancy detection**: Automatically activates comfort controls when workspace is occupied
- **Cloud-based management**: User preferences stored and retrieved from AWS cloud
- **Real-time monitoring**: Web dashboard for viewing current conditions and adjusting preferences
- **Energy optimization**: Only activates comfort controls when workspace is occupied
- **Remote control**: Update comfort settings from anywhere via the web interface

## System Architecture

![System Architecture](./docs/images/architecture.png)

### Hardware Components

- Raspberry Pi 4 (central controller)
- SenseHat (temperature, humidity, LED matrix display)
- PIR motion sensor (occupancy detection)
- DHT22 temperature/humidity sensor (optional, for more accurate readings)
- GPIO-controlled fan (local airflow control)

### Cloud Infrastructure

- **AWS IoT Core**: Secure device connectivity using MQTT
- **Device Shadow**: Virtual representation of the device state
- **DynamoDB**: Stores user preferences and telemetry data
- **Lambda**: API handlers for web interface
- **API Gateway**: RESTful API endpoints
- **S3**: Hosts static web dashboard

## Repository Structure

```
├── Cloud/                    # AWS Lambda functions and cloud components
│   ├── PCZS_PreferncesHandler/   # Lambda for handling user preferences
│   └── PCZS_TelemetryHandler/    # Lambda for handling telemetry data
├── Sensors/                  # Raspberry Pi sensor code
│   ├── integrated_sensor.py  # Combined script for all sensors
│   ├── sensehat_sensor.py    # SenseHat-only mode
│   └── pir_sensor.py         # PIR sensor-only mode
├── scripts/                  # Setup and utility scripts
│   └── aws_setup.sh          # AWS resource creation script
├── web/                      # Web dashboard files
│   ├── index.html            # Main dashboard page
│   └── api_gateway.js        # API integration
└── requirements.txt          # Python dependencies
```

## Getting Started

### Prerequisites

- Raspberry Pi 4 with Raspbian OS
- SenseHat or compatible sensors
- AWS account (free tier works for testing)
- Python 3.7+ and pip

### Hardware Setup

1. Connect the SenseHat to your Raspberry Pi
2. Wire the PIR motion sensor to GPIO pin 17
3. (Optional) Connect the DHT22 temperature/humidity sensor to GPIO pin 4
4. (Optional) Connect the fan control relay to GPIO pins 22/23/24 for RGB status indicators

### Software Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/Personalized-Comfort-Zones-System.git
cd Personalized-Comfort-Zones-System

# Install dependencies
pip install -r requirements.txt

# Create certificate directory
mkdir -p ~/pczs/cert
```

### AWS Setup

1. Create an AWS account if you don't have one
2. Run the AWS setup script (or follow manual setup instructions below)

```bash
cd scripts
./aws_setup.sh
```

3. Update the endpoint in your sensor scripts with your AWS IoT endpoint

### Manual AWS Setup (if not using script)

1. In AWS IoT Core, create a Thing named "PCZS"
2. Create certificates and download them to the ~/pczs/cert directory
3. Create a policy allowing IoT access and attach it to your certificate
4. Create the DynamoDB tables:
   - PCZS_Telemetry (partition key: workspace_id, sort key: timestamp)
   - PCZS_UserPreferences (partition key: user_id, sort key: workspace_id)
5. Set up Lambda functions and API Gateway as per the implementation guide

### Running the System

```bash
# Start the integrated sensor script
cd Sensors
python integrated_sensor.py
```

### Web Dashboard Setup

1. Upload the contents of the `web` directory to an S3 bucket configured for static website hosting
2. Update the API_ENDPOINT in api_gateway.js with your API Gateway URL
3. Access the dashboard through the S3 website URL

## Usage

1. Access the web dashboard from any browser
2. Set your preferred temperature and humidity along with tolerance thresholds
3. The system will automatically maintain your comfort settings when you're at your workspace
4. LED indicators show comfort status (green = comfortable, red = too hot, blue = too cold)

## Advanced Usage

### Different Sensor Modes

The system can run in three different modes:

- **Integrated mode** (integrated_sensor.py): Uses all available sensors for complete functionality
- **SenseHat mode** (sensehat_sensor.py): Uses only the SenseHat for temperature/humidity sensing
- **PIR mode** (pir_sensor.py): Uses only the PIR sensor for occupancy detection

### Adding Multiple Workspaces

To add more workspaces:

1. Create additional Raspberry Pi setups with sensors
2. Update the WORKSPACE_ID in the sensor script for each setup
3. Add the new workspace to the dropdown in the web interface

## Troubleshooting

### Common Issues

- **Connection failures**: Check your certificates and endpoint URL
- **No sensor readings**: Verify sensor connections and try running in different modes
- **Shadow updates not working**: Verify MQTT topics and check AWS IoT permissions

### Logs

Check logs for debugging:

```bash
# On Raspberry Pi
tail -f ~/pczs/logs/pczs.log

# In AWS
Check CloudWatch logs for Lambda functions
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- AWS IoT Documentation
- Raspberry Pi Foundation
- SenseHat library developers

## Future Work

- PID-based fan control for smoother temperature regulation
- Machine learning for predictive comfort settings based on user behavior
- Multi-user workspace sharing with preference prioritization
- Integration with building HVAC systems for more efficient energy usage
