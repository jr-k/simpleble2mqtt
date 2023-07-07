#!/usr/bin/python3

import asyncio
import time
import math
import yaml
import json
import signal
import argparse
import threading
import sys
import os
import logging

from bleak import BleakScanner
from paho.mqtt import client as mqtt_client

verbose = False

#####################################
#       Helpers
#####################################

def log(msg):
    global verbose
    if verbose:
        print(msg)
    logging.info(msg)

class SingleStateKalmanFilter():
    def __init__(self, a, b, c, x, p, q, r):
        self.__A = a
        self.__B = b
        self.__C = c
        self.__current_state_estimate = x
        self.__current_prob_estimate = p
        self.__Q = q
        self.__R = r

    def current_state(self):
        return self.__current_state_estimate

    def step(self, control_input, measurement):
        # prediction step
        predicted_state_estimate = self.__A * self.__current_state_estimate + self.__B * control_input
        predicted_prob_estimate = (self.__A * self.__current_prob_estimate) * self.__A + self.__Q

        # innovation step
        innovation = measurement - self.__C * predicted_state_estimate
        innovation_covariance = self.__C * predicted_prob_estimate * self.__C + self.__R

        # update step
        kalman_gain = predicted_prob_estimate * self.__C * 1 / float(innovation_covariance)
        self.__current_state_estimate = predicted_state_estimate + kalman_gain * innovation

        # eye(n) = nxn identity matrix
        self.__current_prob_estimate = (1 - kalman_gain * self.__C) * predicted_prob_estimate

#####################################
#       Configuration Setup
#####################################

if not os.path.isfile("config.yaml"):
    log("Configuration file config.yaml does not exist, copy from config.yaml.dist then run again")
    sys.exit(1)

# Load configuration from config.yaml
with open("config.yaml", "r") as file:
    config = yaml.safe_load(file)

# MQTT configuration
mqtt_config = config["mqtt"]
client = mqtt_client.Client(mqtt_config["client_id"])
if "username" in mqtt_config and "password" in mqtt_config:
    client.username_pw_set(mqtt_config["username"], mqtt_config["password"])
client.connect(mqtt_config["broker"], mqtt_config["port"])

# Beacon configuration
devices_config = {device["address"]: device for device in config["devices"]}
devices_to_track = [device.lower() for device in devices_config.keys()]
tag_detected = {device: False for device in devices_to_track}
rssi_values = {device: None for device in devices_to_track}
status_interval_threshold = {device: 0 for device in devices_to_track}
previous_status = {device: None for device in devices_to_track}

#####################################
#       ACTION: Calibrate
#####################################

class Calibrator():
    def __init__(self):
        self.scanner = BleakScanner()

    async def scan(self, period=10):
        await asyncio.sleep(period)  # to simulate the scan period
        return await self.scanner.discover()

    def get_n(self, mr, rssi, distance=1.0):
        return 2 + abs(((mr - rssi) * math.log(math.e, 10)) / 10)

    def get_distance(self, rssi, mr, n):
        if n == 0:
            return -1
        return math.pow(10, (mr - rssi) / (10 * n))

async def calibrate(maclist):
    scanner = Calibrator()
    devlist = {}
    calibrator_period = 10

    while True:
        devices = await scanner.scan(period=calibrator_period)
        for dev in devices:
            if len(maclist) > 0 and dev.address.lower() not in maclist:
                continue

            rssi = dev.rssi

            if dev.address.lower() not in devlist.keys():
                a = 1  # no process innovation
                c = 1  # measurement
                b = 0  # no control input
                q = 0.005  # process covariance
                r = 1  # measurement covariance
                x = rssi  # initial estimate
                p = 1  # initial covariance
                devlist[dev.address.lower()] = SingleStateKalmanFilter(a, b, c, x, p, q, r)

            devlist[dev.address.lower()].step(0, abs(rssi))

            # calculate distance with the smoothed RSSI
            frssi = -1 * devlist[dev.address.lower()].current_state()
            n = scanner.get_n(frssi, rssi)
            dist = scanner.get_distance(rssi, frssi, n)
            print("{} ({}), RSSI={} dB, MR={:.4f}, N={:.8f}, Distance={:.2f}".format(dev.address.lower(), dev.name, rssi, frssi, n, dist))
    await asyncio.sleep(calibrator_period + 3)

#####################################
#       ACTION: Scan
#####################################

def publish(status, device, message, subtopic = None):
    if previous_status[device] is None or status != previous_status[device]:
        topic = mqtt_config['topic']

        if subtopic:
            topic = f"{topic}/{subtopic}"

        client.publish(f"{topic}", json.dumps(message))

        previous_status[device] = status
    else:
        log(f"No changes for device {device} ({subtopic})")

async def scan(verbose):
    scanner = BleakScanner(detection_callback=detection_callback)

    while True:
        devices = await scanner.start()
        await asyncio.sleep(config["interval"])
        await scanner.stop()

        for device in devices_to_track:
            device = device.lower()
            subtopic = devices_config[device]['topic']
            status = False
            distance = -1

            # Vérifier si le tag a été détecté ou non
            if tag_detected[device]:
                distance = round(calculate_distance(device, rssi_values[device]), 2)
                status = True
                tag_detected[device] = False

            message = {
                "detected": status,
                "distance": distance,
                "rssi": rssi_values[device],
                "payload": devices_config[device]['payload']
            }

            # Check if device has been detected
            if status:
                if verbose:
                    log(f"Device {device} ({subtopic}) detected at distance: {message['distance']} meters")
                publish(status, device, message, subtopic)
                status_interval_threshold[device] = 0  # Reset status count if tag detected
            else:
                status_interval_threshold[device] += 1  # Increase status count
                if status_interval_threshold[device] >= config["status_interval_threshold"]:
                    if verbose:
                        log(f"Device {device} ({subtopic}) not detected")
                    publish(status, device, message, subtopic)
                    status_interval_threshold[device] = 0  # Reset status count after sending not detected message
                else:
                    if verbose:
                        currentCheck = status_interval_threshold[device]
                        maxCheck = config["status_interval_threshold"]
                        log(f"Device {device} ({subtopic}) not detected but waiting for more confirmations {currentCheck}/{maxCheck}")

            tag_detected[device] = False
            rssi_values[device] = None

def detection_callback(device, advertisement_data):
    device_address = device.address.lower()
    # Check if detected device is in our beacon list
    if device_address in devices_to_track:
        tag_detected[device_address] = True
        rssi_values[device_address] = advertisement_data.rssi

def calculate_distance(device, rssi):
    """ Calculate distance based on RSSI """
    return 10 ** ((devices_config[device]["ble"]["MR"] - rssi) / (10 * devices_config[device]["ble"]["N"]))

#####################################
#       MAIN
#####################################

def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-c", "--calibrate", help="Start calibrate for devices showing the avearage RSSI 1 meter away", action="store_true")
    group.add_argument("-s", "--scan", help="Start daemon for registered devices", action="store_true")
    parser.add_argument("-d", "--device", nargs='+', help="Filter by device mac when scanning", default=[])
    parser.add_argument("-v", "--verbose", help="Run in verbose mode", action="store_true", default=False)
    args = parser.parse_args()
    global verbose
    verbose = args.verbose

    print("Simpleble2mqtt 1.0\n=========")

    if args.scan:
        log("Scanning...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(scan(args.verbose))
    elif args.calibrate:
        log("Calibrating...")
        loop = asyncio.get_event_loop()
        loop.run_until_complete(calibrate(args.device))

if __name__ == "__main__":
    main()



