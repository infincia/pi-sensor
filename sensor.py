#!/usr/bin/env python

import sys
import os

import time
import psutil
import platform
import logging
import time
import argparse
import json

import anyconfig

conf = anyconfig.load(["/opt/pi-sensor/defaults.toml", "/etc/pi-sensor/config.toml"], ignore_missing=True, ac_merge=anyconfig.MS_REPLACE)

update_interval = conf['update_interval']

si7021_enabled = conf['si7021']['enabled']
rfm69_enabled = conf['rfm69']['enabled']
awsiot_enabled = conf['awsiot']['enabled']
mqtt_enabled = conf['mqtt']['enabled']

disk_enabled = conf['disk']['enabled']
mem_enabled = conf['mem']['enabled']
cpu_enabled = conf['cpu']['enabled']

DEVICE_NAME = conf['name']

print "Pi Sensor {0} running".format(DEVICE_NAME)

if si7021_enabled:
	print "si7021 enabled"
	import Adafruit_PureIO.smbus as smbus


if rfm69_enabled:
	print "RFM69 enabled"
	rfm69_high_power = conf['rfm69']['high_power']
	rfm69_network = conf['rfm69']['network']
	rfm69_node = conf['rfm69']['node']
	rfm69_gateway = conf['rfm69']['gateway']

	rfm69_encryption_key = conf['rfm69']['encryption_key']

	from RFM69 import RFM69
	from RFM69.RFM69registers import *

	radio = RFM69.RFM69(freqBand = RF69_915MHZ, nodeID = rfm69_node, networkID = rfm69_network, isRFM69HW = True, intPin = 18, rstPin = 22, spiBus = 0, spiDevice = 0)

	radio.rcCalibration()
	radio.setHighPower(rfm69_high_power)
	radio.encrypt(rfm69_encryption_key)

if awsiot_enabled:
	print "AWS IoT enabled"
	from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

	awsiot_endpoint = conf['awsiot']['endpoint']
	awsiot_ca = conf['awsiot']['ca']
	awsiot_cert = conf['awsiot']['cert']
	awsiot_key = conf['awsiot']['key']

	awsiot = AWSIoTMQTTClient(DEVICE_NAME)
	awsiot.configureEndpoint(awsiot_endpoint, 8883)
	awsiot.configureCredentials(awsiot_ca, awsiot_key, awsiot_cert)
	awsiot.configureOfflinePublishQueueing(-1)
	awsiot.configureDrainingFrequency(2)
	awsiot.configureConnectDisconnectTimeout(10)
	awsiot.configureMQTTOperationTimeout(5)


if mqtt_enabled:
	print "MQTT enabled"
	import paho.mqtt.client as mqtt

	mqtt_endpoint = conf['mqtt']['endpoint']
	mqtt_port = conf['mqtt']['port']

	def on_mqtt_connect(client, userdata, flags, rc):
	    print("MQTT connected with result code "+str(rc))

	    # Subscribing in on_connect() means that if we lose the connection and
	    # reconnect then subscriptions will be renewed.
	    client.subscribe("$SYS/#")

	# The callback for when a PUBLISH message is received from the server.
	def on_mqtt_message(client, userdata, msg):
	    print("MQTT message <" + msg.topic + ">: " + str(msg.payload))

	mqtt_client = mqtt.Client()
	mqtt_client.on_connect = on_mqtt_connect
	mqtt_client.on_message = on_mqtt_message


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

def push_sensor_values(temperature, humidity):
	if awsiot_enabled:
		try:
			awsiot.publish(DEVICE_NAME + '/temperature', "{0:.2f}".format(temperature), 0)
			awsiot.publish(DEVICE_NAME + '/humidity', "{0:.2f}".format(humidity), 0)
		except Exception as e:
			print("Warning: failed to push sensor values to awsiot")

	if mqtt_enabled:
		try:
			mqtt_client.publish(DEVICE_NAME + '/temperature', "{0:.2f}".format(temperature), 0)
			mqtt_client.publish(DEVICE_NAME + '/humidity', "{0:.2f}".format(humidity), 0)
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
	except Exception as e:
		print("Warning: failed to get disk data: ", e)

	return disk_percent


def push_disk_stats(disk_percent):
	if awsiot_enabled:
		try:
			awsiot.publish(DEVICE_NAME + '/disk', "{0:.2f}".format(disk_percent), 0)
		except Exception as e:
			print("Warning: failed to push disk stats to awsiot: ", e)

	if mqtt_enabled:
		try:
			mqtt_client.publish(DEVICE_NAME + '/disk', "{0:.2f}".format(disk_percent), 0)
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


def push_mem_stats(mem_percent):
	if awsiot_enabled:
		try:
			awsiot.publish(DEVICE_NAME + '/ram', "{0:.2f}".format(mem_percent), 0)
		except Exception as e:
			print("Warning: failed to push mem stats to awsiot: ", e)

	if mqtt_enabled:
		try:
			mqtt_client.publish(DEVICE_NAME + '/ram', "{0:.2f}".format(mem_percent), 0)
		except Exception as e:
			print("Warning: failed to push mem stats to mqtt: ", e)

def push_cpu_stats(cpu_percent):
	if awsiot_enabled:
		try:
			awsiot.publish(DEVICE_NAME + '/cpu', "{0:.2f}".format(cpu_percent), 0)
		except Exception as e:
			print("Warning: failed to push cpu stats to awsiot: ", e)

	if mqtt_enabled:
		try:
			mqtt_client.publish(DEVICE_NAME + '/cpu', "{0:.2f}".format(cpu_percent), 0)
		except Exception as e:
			print("Warning: failed to push cpu stats to mqtt: ", e)







def loop():
	print 'Connecting...'
	if awsiot_enabled:
		awsiot.connect()

	if mqtt_enabled:
		mqtt_client.connect(mqtt_endpoint, mqtt_port, 60)
		mqtt_client.loop_start()


	last = time.time()

	while True:
		time.sleep(0.1)

		now = time.time()
		if now - last > update_interval:
			last = now

			sensor_message = { "n": DEVICE_NAME, "ty": "hello" }

			if si7021_enabled:
				temperature, humidity = get_sensor_values()
				if temperature is not None and humidity is not None:
					push_sensor_values(temperature, humidity)
					sensor_message["t"] = "{0:.2f}".format(temperature)
					sensor_message["h"] = "{0:.2f}".format(humidity)

			if disk_enabled:
				disk_percent = get_disk_stats()
				if disk_percent is not None:
					push_disk_stats(disk_percent)
					sensor_message["d"] = "{0:.2f}".format(disk_percent)

			if mem_enabled:
				mem_percent = get_mem_stats()
				if mem_percent is not None:
					push_mem_stats(mem_percent)
					sensor_message["m"] = "{0:.2f}".format(mem_percent)

			if cpu_enabled:
				cpu_percent = get_cpu_stats()
				if cpu_percent is not None:
					push_cpu_stats(cpu_percent)
					sensor_message["c"] = "{0:.2f}".format(cpu_percent)

			json_packet = json.dumps(sensor_message, sort_keys = True)

			if rfm69_enabled:
				print "Sending %s to %s" % (json_packet, rfm69_gateway)
				if radio.sendWithRetry(rfm69_gateway, json_packet, 3, 20):
					print "Radio ack recieved"

		if rfm69_enabled:
			radio.receiveBegin()
			if not radio.receiveDone():
				continue

			received_message = "".join([chr(letter) for letter in radio.DATA])

			print "Received message from %s<%s dB>" % (radio.SENDERID, radio.RSSI)

			if radio.ACKRequested():
				radio.sendACK()


			if radio.SENDERID != rfm69_gateway:
				continue

			try:
				command_message = json.loads(received_message)
				command = command_message['c']
				if command == 'reboot':
					print "Pi Sensor %s rebooting..." % DEVICE_NAME
					os.system('reboot')
				else:
					print "Recevied unknown command: %s" % command
			except:
				print "Received invalid JSON message, ignoring: %s" % received_message


if __name__ == "__main__":
	try:
		loop()
	except Exception as e:
		print "Exception occurred during loop: {0}".format(e)
	finally:
		if rfm69_enabled:
			# try to ensure everything gets reset
			radio.shutdown()
			mqtt_client.loop_stop(force = True)
