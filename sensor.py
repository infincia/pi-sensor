#!/usr/bin/env python

import sys

import time
import psutil
import platform
import logging
import time
import argparse
import json


import Adafruit_PureIO.smbus as smbus
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

DEVICE_NAME = platform.node()


mqtt = AWSIoTMQTTClient(DEVICE_NAME)
mqtt.configureEndpoint("a2ilo8j9t13k8m.iot.us-east-1.amazonaws.com", 8883)
mqtt.configureCredentials("/etc/aws/root-CA.crt", "/etc/aws/Picam1.private.key", "/etc/aws/Picam1.cert.pem")
mqtt.configureOfflinePublishQueueing(-1)
mqtt.configureDrainingFrequency(2)
mqtt.configureConnectDisconnectTimeout(10)
mqtt.configureMQTTOperationTimeout(5)

def update_sensor():
	try:
		# Get I2C bus
		bus = smbus.SMBus(1)

		# SI7021 address, 0x40(64)
		#		0xF5(245)	Select Relative Humidity NO HOLD master mode
		bus.write_byte(0x40, 0xF5)

		time.sleep(0.3)

		# SI7021 address, 0x40(64)
		# Read data back, 2 bytes, Humidity MSB first
		data0 = bus.read_byte(0x40)
		data1 = bus.read_byte(0x40)

		# Convert the data
		humidity = ((data0 * 256 + data1) * 125 / 65536.0) - 6

		time.sleep(0.3)

		# SI7021 address, 0x40(64)
		#		0xF3(243)	Select temperature NO HOLD master mode
		bus.write_byte(0x40, 0xF3)

		time.sleep(0.3)

		# SI7021 address, 0x40(64)
		# Read data back, 2 bytes, Temperature MSB first
		data0 = bus.read_byte(0x40)
		data1 = bus.read_byte(0x40)

		# Convert the data
		temperature = ((data0 * 256 + data1) * 175.72 / 65536.0) - 46.85

		#humidity, temperature = Adafruit_DHT.read_retry(11, DHT_PIN)
		fahrenheit = (temperature * 1.8) + 32

		mqtt.publish(DEVICE_NAME + '/temperature', fahrenheit, 0)
		mqtt.publish(DEVICE_NAME + '/humidity', humidity, 0)
	except Exception as e:
		print("Warning: failed to get sensor data: ", e)
		pass


def update_disk():
	try:
		disk = psutil.disk_usage('/')
		free = round(disk.free/1024.0/1024.0/1024.0,1)
		total = round(disk.total/1024.0/1024.0/1024.0,1)
		used = total - free
		disk_percent = (used / total) * 100.0
		mqtt.publish(DEVICE_NAME + '/disk', disk_percent, 0)
	except Exception as e:
		print("Warning: failed to get disk data: ", e)
		pass


def update_stats():
	try:
		cpu_percent = psutil.cpu_percent()
		memory = psutil.virtual_memory()
		available = round(memory.available/1024.0/1024.0,1)
		total = round(memory.total/1024.0/1024.0,1)
		used = total - available
		mem_percent = (used / total) * 100.0
		mqtt.publish(DEVICE_NAME + '/ram', mem_percent, 0)
		mqtt.publish(DEVICE_NAME + '/cpu', cpu_percent, 0)
	except Exception as e:
		print("Warning: failed to update mqtt: ", e)
		pass


def loop():
	print 'Connecting...'
	mqtt.connect()

	while True:
		update_sensor()
		update_disk()
		update_stats()

		time.sleep(60)


if __name__ == "__main__":

	loop()
