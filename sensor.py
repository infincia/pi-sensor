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
mqtt.configureCredentials("/etc/aws/root-CA.crt", "/etc/aws/" + DEVICE_NAME + ".private.key", "/etc/aws/" + DEVICE_NAME + ".cert.pem")
mqtt.configureOfflinePublishQueueing(-1)
mqtt.configureDrainingFrequency(2)
mqtt.configureConnectDisconnectTimeout(10)
mqtt.configureMQTTOperationTimeout(5)




def get_sensor_values():
	temperature = None
	humidity = None

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

		# Convert celsius to fahrenheit
		temperature = (temperature * 1.8) + 32

	except Exception as e:
		print("Warning: failed to get sensor data: ", e)

	return temperature, humidity

def push_sensor_values_mqtt(temperature, humidity):
	try:
		mqtt.publish(DEVICE_NAME + '/temperature', "{0:.2f}".format(temperature), 0)
		mqtt.publish(DEVICE_NAME + '/humidity', "{0:.2f}".format(humidity), 0)
	except Exception as e:
		print("Warning: failed to push sensor values to mqtt")




def get_disk_stats():
	disk_percent = None

	try:
		disk = psutil.disk_usage('/')
		free = round(disk.free/1024.0/1024.0/1024.0,1)
		total = round(disk.total/1024.0/1024.0/1024.0,1)
		used = total - free
		disk_percent = (used / total) * 100.0
		mqtt.publish(DEVICE_NAME + '/disk', disk_percent, 0)
	except Exception as e:
		print("Warning: failed to get disk data: ", e)

	return disk_percent


def push_disk_stats_mqtt(disk_percent):
	try:
		mqtt.publish(DEVICE_NAME + '/disk', "{0:.2f}".format(disk_percent), 0)
	except Exception as e:
		print("Warning: failed to push disk stats to mqtt: ", e)




def get_mem_stats():
	mem_percent = None

	try:
		memory = psutil.virtual_memory()
		available = round(memory.available/1024.0/1024.0,1)
		total = round(memory.total/1024.0/1024.0,1)
		used = total - available
		mem_percent = (used / total) * 100.0
		mqtt.publish(DEVICE_NAME + '/ram', mem_percent, 0)
		mqtt.publish(DEVICE_NAME + '/cpu', cpu_percent, 0)
	except Exception as e:
		print("Warning: failed to get mem stats: ", e)

	return mem_percent


def get_cpu_stats():
	cpu_percent = None

	try:
		cpu_percent = psutil.cpu_percent()
	except Exception as e:
		print("Warning: failed to get cpu stats: ", e)

	return cpu_percent


def push_mem_stats_mqtt(mem_percent):
	try:
		mqtt.publish(DEVICE_NAME + '/ram', "{0:.2f}".format(mem_percent), 0)
	except Exception as e:
		print("Warning: failed to push mem stats to mqtt: ", e)

def push_cpu_stats_mqtt(cpu_percent):
	try:
		mqtt.publish(DEVICE_NAME + '/cpu', "{0:.2f}".format(cpu_percent), 0)
	except Exception as e:
		print("Warning: failed to push cpu stats to mqtt: ", e)





def loop():
	print 'Connecting...'
	mqtt.connect()

	last = time.time()

	while True:
		time.sleep(0.1)

		now = time.time()
		if now - last > 60:
			last = now

			temperature, humidity = get_sensor_values()
			if temperature is not None and humidity is not None:
				push_sensor_values_mqtt(temperature, humidity)

			disk_percent = get_disk_stats()
			if disk_percent is not None:
				push_disk_stats_mqtt(disk_percent)
			mem_percent = get_mem_stats()

			if mem_percent is not None:
				push_mem_stats_mqtt(mem_percent)
			cpu_percent = get_cpu_stats()

			if cpu_percent is not None:
				push_cpu_stats_mqtt(cpu_percent)


if __name__ == "__main__":
	try:
		loop()
	except Exception as e:
		print "Exception occurred during loop: {0}".format(e)
