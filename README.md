# simpleble2mqtt

## MQTT Bluetooth Low Energy beacon tracker

Every time a BLE beacon is received, it applies a Kalman filter to smooth the RSSI and reduce the noise to make the system more accurate.

[Home Assistant](https://www.home-assistant.io/) compatible.

## Prerequisites

- On Debian based machines:
```
sudo apt-get install python3-pip python3-setuptools python3-dev libglib2.0-dev build-essential git
```

- Clone the repository
```
git clone https://github.com/jr-k/simpleble2mqtt.git
cd simpleble2mqtt
```

- Install Python dependencies:
```
sudo pip3 install -r requirements.txt
```
- Check bluetooth device state:
```
sudo hciconfig hci0 down && sudo hciconfig hci0 up
```
If you receive `Can't init device hci0: Operation not possible due to RF-kill (132)` execute:
```
connmanctl enable bluetooth
```

## General setup

### Calibration

**IMPORTANT**: Before running any scan, take the BLE device 1 meter away from the BLE scanner device.

To discover devices as well as calculate the "**MR**" and the "**N**" constant, run the script with the following arguments:

```
python3 simpleble2mqtt.py -s -d [device-mac-here]
```

***Note**: To see all the devices in range, remove the "--device [device-mac-here]" argument

Let that scan run for a while, and once the "distance" variable is close to 1 meter and "stable" between different samples, stop the scan by pressing "CTRL+C" and write down the "**MR**" and "**N**" variables.

Sample output:
```
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-0.1671, N=4.90251674, Distance=23.08
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-75 dB, MR=-25.3183, N=4.15764916, Distance=15.67
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-77 dB, MR=-38.4631, N=3.67363437, Distance=11.19
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-77 dB, MR=-46.3992, N=3.32897478, Distance=8.30
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-72 dB, MR=-50.8587, N=2.91815640, Distance=5.30
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-77 dB, MR=-54.8311, N=2.96278122, Distance=5.60
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-76 dB, MR=-57.7031, N=2.79462608, Distance=4.52
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-58.8496, N=2.35396926, Distance=2.22
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-76 dB, MR=-60.8000, N=2.66012685, Distance=3.73
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-72 dB, MR=-61.9886, N=2.43478816, Distance=2.58
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-63.3710, N=2.15760607, Distance=1.47
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-72 dB, MR=-64.1557, N=2.34067466, Distance=2.16
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-64.4047, N=2.11271405, Distance=1.33
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-77 dB, MR=-65.4715, N=2.50067683, Distance=2.89
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-76 dB, MR=-66.3382, N=2.41960843, Distance=2.51
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-69.6263, N=2.11405924, Distance=0.75
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-71 dB, MR=-69.5530, N=2.06284109, Distance=1.18
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-71 dB, MR=-69.6518, N=2.05855109, Distance=1.16
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-69.4929, N=2.10826675, Distance=0.76
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-69.3228, N=2.10087613, Distance=0.78
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-67 dB, MR=-69.1642, N=2.09399012, Distance=0.79
ca:fe:ca:fe:ca:fe (BLE Device), RSSI=-70 dB, MR=-69.6756, N=2.01408935, Distance=1.04
```

In this case, let's write down:
 - **MR**: -69.6756
 - **N**: 2.01408935

## Configuration

Before running the BLE tracker, you need to configure some settings in `config.yaml`.
Run `cp config.yaml.dist config.yaml`

```yaml
interval: 5                     # Scan interval in seconds
status_interval_threshold: 3    # Max interval to trigger status change [status_interval_threshold * interval] seconds
mqtt:
  broker: host                  # Mqtt server host
  port: 1883                    # Mqtt server port
  username:                     # Mqtt server username (remove key if unused)
  password:                     # Mqtt server password (remove key if unused)
  client_id:                    # Unique client id
  topic: ble_tag/status         # Mqtt root topic
devices:
  - address: xx:xx:xx:xx:xx:xx  # Mac address of ble tag
    topic: user1                # Subtopic for this device
    payload: tag1               # Custom payload injected in JSON 
    ble:        
      MR: -77.8746              # Measured RSSI obtained with calibration
      N: 2.00544811             # N obtained with calibration
```

## Installation

1. Move the project folder to your prefered location
2. Edit the `simpleble2mqtt.service` and set the right paths to `WorkingDirectory` and `ExecStart`
3. Adjust your settings in `config.yaml`
4. Install the service and start
```
sudo cp simpleble2mqtt.service /etc/systemd/system/
sudo systemctl enable simpleble2mqtt
sudo systemctl start simpleble2mqtt
```

## Message format

### Detected

```bash
# topic: ble_tracker/status/user1
{"detected": true, "distance": 1.14, "rssi": -79, "payload": "tag1"}
```

### Not detected
```bash
# topic: ble_tracker/status/user1
{"detected": false, "distance": -1, "rssi": null, "payload": "tag2"}
```


## Home Assistant integration

### Tracker detection entity

```
sensor:
  - platform: mqtt_room
    name: ble_tag_user1
    device_id: xx:xx:xx:xx:xx:xx
    state_topic: ble_tag
    timeout: 60
    away_timeout: 360
```

[Home Assistant sensor.mqtt_room](https://www.home-assistant.io/integrations/mqtt_room/)

### Binary detection entity

```
binary_sensor:
  - platform: mqtt
    name: Tracked device on user1
    state_topic: "ble_tag/user1"
    value_template: "{{ value_json.detected }}"
    payload_on: "True"
    payload_off: "False"
    off_delay: 120
```

[Home Assistant binary_sensor.mqtt](https://www.home-assistant.io/integrations/binary_sensor.mqtt/)

## Kalman Filter

- [PyConAu2016](https://pyvideo.org/events/pycon-au-2016.html) - [Working with real-time data streams in Python](https://www.youtube.com/watch?v=gFeTkB8VHpw)
- GitHub repository (Lian Blackhall) - https://github.com/lblackhall/pyconau2016

## Related projects

- https://github.com/sch3m4/mqtt-ble-tracker
- https://github.com/mKeRix/room-assistant
- https://github.com/happy-bubbles/presence
- https://jptrsn.github.io/ESP32-mqtt-room/
- https://github.com/1technophile/OpenMQTTGateway
