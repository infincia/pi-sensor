#!/usr/bin/env python3

import argparse
import asyncio
import datetime
import io
import json
import logging
import os
import platform
from queue import Queue, Empty, Full
import socket
import sys
from threading import Thread
import time
import uuid

import Adafruit_PureIO.smbus as smbus
from aiohttp import ClientSession
import anyconfig
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTShadowClient
import msgpack
import nnpy
import paho.mqtt.client as mqtt
import picamera
import prctl
import psutil
from RFM69 import RFM69
from RFM69.RFM69registers import RF69_915MHZ

from zeroconf import ServiceInfo, Zeroconf

from webapi import web_loop

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)


conf = anyconfig.load(["/opt/pi-sensor/defaults.toml", "/etc/pi-sensor/config.toml"], ignore_missing=True, ac_merge=anyconfig.MS_REPLACE)

web_enabled = conf['web']['enabled']
si7021_enabled = conf['si7021']['enabled']
rfm69_enabled = conf['rfm69']['enabled']
awsiot_enabled = conf['awsiot']['enabled']
mqtt_enabled = conf['mqtt']['enabled']
camera_enabled = conf['camera']['enabled']
websocket_enabled = conf['websocket']['enabled']

disk_enabled = conf['disk']['enabled']
mem_enabled = conf['mem']['enabled']
cpu_enabled = conf['cpu']['enabled']

DEVICE_NAME = conf['name']

logger.info("Pi Sensor %s running", DEVICE_NAME)

if web_enabled:
    port = conf['web']['port']


if si7021_enabled:
    logger.info("si7021 enabled")


if rfm69_enabled:
    logger.info("RFM69 enabled")
    rfm69_high_power = conf['rfm69']['high_power']
    rfm69_network = conf['rfm69']['network']
    rfm69_node = conf['rfm69']['node']
    rfm69_gateway = conf['rfm69']['gateway']

    rfm69_encryption_key = conf['rfm69']['encryption_key']

    radio_queue = Queue(maxsize=2)

    radio_shutdown = False


if awsiot_enabled:
    logger.info("AWS IoT enabled")

    awsiot_endpoint = conf['awsiot']['endpoint']
    awsiot_ca = conf['awsiot']['ca']
    awsiot_cert = conf['awsiot']['cert']
    awsiot_key = conf['awsiot']['key']

    awsiot_queue = Queue(maxsize=2)

    awsiot_shutdown = False


if mqtt_enabled:
    logger.info("MQTT enabled")

    mqtt_endpoint = conf['mqtt']['endpoint']
    mqtt_port = conf['mqtt']['port']

    mqtt_queue = Queue(maxsize=2)

    mqtt_shutdown = False

if websocket_enabled:
    websocket_endpoint = conf['websocket']['endpoint']
    websocket_port = conf['websocket']['port']
    gateway_uri = 'wss://{0}:{1}/{2}'.format(websocket_endpoint, websocket_port, platform.node())

    websocket_queue = Queue(maxsize=2)

    websocket_shutdown = False

if camera_enabled:
    streaming_camera = conf['camera']['streaming']
    fps = conf['camera']['fps']
    resolution = conf['camera']['resolution']
    rotation = conf['camera']['rotation']
    shutter_speed = conf['camera']['shutter_speed']
    sensor_mode = conf['camera']['sensor_mode']
    exposure_mode = conf['camera']['exposure_mode']
    use_video_port = conf['camera']['use_video_port']

    camera_shutdown = False


async def get_sensor_values():
    temperature = None
    humidity = None

    try:
        # Get I2C bus
        bus = smbus.SMBus(1)

        # SI7021 address, 0x40(64), command 0xF5(245)
        # Select Relative Humidity NO HOLD master mode
        bus.write_byte(0x40, 0xF5)

        await asyncio.sleep(0.3)

        # SI7021 address, 0x40(64)
        # Read data back, 2 bytes, Humidity MSB first
        data0 = bus.read_byte(0x40)
        data1 = bus.read_byte(0x40)

        # Convert the data
        humidity = ((data0 * 256 + data1) * 125 / 65536.0) - 6

        await asyncio.sleep(0.3)

        # SI7021 address: 0x40(64), command 0xF3(243)
        # Select temperature NO HOLD master mode
        bus.write_byte(0x40, 0xF3)

        await asyncio.sleep(0.3)

        # SI7021 address, 0x40(64)
        # Read data back, 2 bytes, Temperature MSB first
        data0 = bus.read_byte(0x40)
        data1 = bus.read_byte(0x40)

        # Convert the data
        temperature = ((data0 * 256 + data1) * 175.72 / 65536.0) - 46.85

        # Convert celsius to fahrenheit
        temperature = (temperature * 1.8) + 32

    except Exception:
        logger.exception("Failed to get sensor data")

    return temperature, humidity


def get_disk_stats():
    disk_percent = None

    try:
        disk = psutil.disk_usage('/')
        free = round(disk.free / 1024.0 / 1024.0 / 1024.0, 1)
        total = round(disk.total / 1024.0 / 1024.0 / 1024.0, 1)
        used = total - free
        disk_percent = (used / total) * 100.0
    except Exception:
        logger.exception("Failed to get disk data")

    return disk_percent


def get_mem_stats():
    mem_percent = None

    try:
        memory = psutil.virtual_memory()
        available = round(memory.available / 1024.0 / 1024.0, 1)
        total = round(memory.total / 1024.0 / 1024.0, 1)
        used = total - available
        mem_percent = (used / total) * 100.0
    except Exception:
        logger.exception("Failed to get mem stats")

    return mem_percent


def get_cpu_stats():
    cpu_percent = None

    try:
        cpu_percent = psutil.cpu_percent()
    except Exception:
        logger.exception("Failed to get cpu stats")

    return cpu_percent


def get_local_ip():
    # https://stackoverflow.com/a/28950776
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except (socket.error, IndexError):
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def get_local_mac():
    mac_num = hex(uuid.getnode()).replace('0x', '').replace('L', '')
    mac_num = mac_num.zfill(12)
    mac = '-'.join(mac_num[i: i + 2] for i in range(0, 11, 2))
    return mac


def capture_image():
    _image_stream = io.BytesIO()
    camera.annotate_background = picamera.Color('black')
    camera.annotate_text = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    camera.capture(_image_stream, format = 'jpeg', quality = 10, thumbnail = None, use_video_port = use_video_port)
    _image_stream.seek(0)
    _last_image = _image_stream.getvalue()
    _image_stream.close()
    return _last_image


def radio_loop():
    logger.info('Starting radio loop...')

    radio = RFM69.RFM69(freqBand = RF69_915MHZ, nodeID = rfm69_node, networkID = rfm69_network, isRFM69HW = True, intPin = 18, rstPin = 22, spiBus = 0, spiDevice = 0)

    radio.rcCalibration()
    radio.setHighPower(rfm69_high_power)
    radio.encrypt(rfm69_encryption_key)

    while True:
        time.sleep(0.1)

        if radio_shutdown:
            break

        try:
            packet = radio_queue.get(timeout = 0.1)
            logger.debug("Sending binary packet to %s", rfm69_gateway)
            if radio.sendWithRetry(rfm69_gateway, packet, 3, 20):
                logger.debug("Radio ack recieved")
        except Empty:
            pass

        radio.receiveBegin()
        if not radio.receiveDone():
            continue

        received_message = "".join([chr(letter) for letter in radio.DATA])

        logger.debug("Received message from %s<%s dB>", radio.SENDERID, radio.RSSI)

        if radio.ACKRequested():
            radio.sendACK()

        if radio.SENDERID != rfm69_gateway:
            continue

        try:
            command_message = msgpack.unpack(received_message, use_bin_type = True)
            command = command_message['c']
            if command == 'reboot':
                logger.info("Pi Sensor %s rebooting...", DEVICE_NAME)
                os.system('reboot')
            else:
                logger.warning("Recevied unknown command: %s", command)
        except:
            logger.warning("Received invalid message, ignoring: %s", received_message)

    logger.info("radio shutting down")

    radio.shutdown()


def _websocket_loop():
    prctl.set_name("websocket_loop")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    websocket_task = loop.create_task(websocket_loop())

    loop.run_forever()

async def websocket_loop():
    logger.info('Starting websocket loop...')

    session = ClientSession()

    websocket = None

    while True:
        await asyncio.sleep(0.1)

        if websocket_shutdown:
            await websocket.close()
            await session.close()
            break

        if websocket is None:
            logger.info('Websocket not connected, reconnecting')
            try:
                websocket = await session.ws_connect(gateway_uri, timeout = 30)
            except:
                logger.info('Websocket connection failed, retrying')
                continue
            logger.info('Websocket connected')

        try:
            packet = websocket_queue.get(block = False)
        except Empty:
            continue
        


        try:
            await websocket.send_bytes(packet)
        except Exception:
            logger.exception('Websocket closed, reconnecting')
            websocket = None



def awsiot_loop():
    logger.info('Starting AWS IoT loop...')

    awsiot = AWSIoTMQTTShadowClient(DEVICE_NAME)
    awsiot.configureEndpoint(awsiot_endpoint, 8883)
    awsiot.configureCredentials(awsiot_ca, awsiot_key, awsiot_cert)
    awsiot.configureConnectDisconnectTimeout(10)
    awsiot.configureMQTTOperationTimeout(5)

    awsiot.connect()
    shadow = awsiot.createShadowHandlerWithName(DEVICE_NAME, True)

    while True:
        time.sleep(0.1)

        if awsiot_shutdown:
            break

        try:
            packet = awsiot_queue.get(timeout = 0.1)

            o = msgpack.unpackb(packet)

            logging.info("aws dict: %s", o)

            doc = {
                "state": {
                    "reported": {
                        "temperature": o[b't'],
                        "humidity": o[b'h']
                    }
                }
            }
            logging.info("aws doc: %s", doc)

            s = json.dumps(doc)
            
            logging.info("aws json: %s", s)

            shadow.shadowUpdate(s, None, 5)
        except Empty:
            pass
        except Exception:
            logger.exception("Failed to push sensor packet to AWS IoT")

    awsiot.disconnect()


async def mqtt_loop():
    prctl.set_name("mqtt_loop")

    logger.info('Starting MQTT loop...')

    def on_mqtt_connect(client, userdata, flags, rc):
        logger.info("MQTT connected with result code: %s", str(rc))

    def on_mqtt_disconnect(client, userdata, rc):
        logger.info("MQTT disconnected with result code: %s", str(rc))

    # The callback for when a PUBLISH message is received from the server.
    def on_mqtt_message(client, userdata, msg):
        logger.info("MQTT message <%s>: %s", msg.topic, str(msg.payload))

    mqtt_client = mqtt.Client()
    mqtt_client.enable_logger(logger)
    mqtt_client.on_connect = on_mqtt_connect
    mqtt_client.on_disconnect = on_mqtt_disconnect
    mqtt_client.on_message = on_mqtt_message

    mqtt_client.connect(mqtt_endpoint, mqtt_port, 60)

    if mqtt_port == 8883:
        logger.info("MQTT configuring TLS")
        try:
            mqtt_client.tls_set()
        except Exception:
            logger.exception("MQTT TLS configuration failed")

    mqtt_client.loop_start()
        
    while True:
        time.sleep(0.1)

        if mqtt_shutdown:
            break

        try:
            packet = mqtt_queue.get(timeout = 0.1)
            mqtt_client.publish(DEVICE_NAME, packet, 0)
        except Empty:
            pass
        except Exception:
            logger.exception("Failed to push sensor packet to mqtt")

    mqtt_client.disconnect()
    mqtt_client.loop_stop(force = True)


def _sensor_loop():
    prctl.set_name("sensor_loop")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    sensor_task = loop.create_task(sensor_loop())

    loop.run_forever()

async def sensor_loop():
    logger.info('Starting sensor loop...')

    while True:
        sensor_message = {"n": DEVICE_NAME}

        if si7021_enabled:
            temperature, humidity = await get_sensor_values()
            if temperature is not None and humidity is not None:
                sensor_message["t"] = temperature
                sensor_message["h"] = humidity

        if disk_enabled:
            disk_percent = get_disk_stats()
            if disk_percent is not None:
                sensor_message["d"] = disk_percent

        if mem_enabled:
            mem_percent = get_mem_stats()
            if mem_percent is not None:
                sensor_message["m"] = mem_percent

        if cpu_enabled:
            cpu_percent = get_cpu_stats()
            if cpu_percent is not None:
                sensor_message["c"] = cpu_percent

        sensor_message['ty'] = "sensor"

        binary_packet = msgpack.packb(sensor_message, use_bin_type = True)

        if websocket_enabled:
            logger.debug("sending sensor packet to websocket")

            try:
                websocket_queue.put(binary_packet, block = False)
            except Full:
                logger.info("websocket queue full")

        if rfm69_enabled:
            logger.debug("sending sensor packet to radio")

            try:
                radio_queue.put(binary_packet, block = False)
            except Full:
                logger.debug("radio queue full")

        if awsiot_enabled:
            logger.debug("sending sensor packet to aws")

            try:
                awsiot_queue.put(binary_packet, block = False)
            except Full:
                logger.debug("aws queue full")

        if mqtt_enabled:
            logger.debug("sending sensor packet to mqtt")

            try:
                mqtt_queue.put(binary_packet, block = False)
            except Full:
                logger.debug("mqtt queue full")

        await asyncio.sleep(60)

def camera_loop():
    logger.info('Starting camera loop...')


    with picamera.PiCamera() as camera:
        camera.rotation = rotation
        camera.resolution = resolution
        camera.framerate = fps
        camera.shutter_speed = shutter_speed
        camera.sensor_mode = sensor_mode
        camera.exposure_mode = exposure_mode
        camera.framerate_range = (0.1, 30)

        camera.start_preview()

        time.sleep(3)

        logger.info('Waiting for camera module warmup...')

        try:
            while True:
                sensor_message = {"n": DEVICE_NAME}

                cap_start = time.time()
                last_image = capture_image(camera)
                cap_end = time.time()
                logger.debug("Capture took %f sec.", (cap_end - cap_start))

                width, height = camera.resolution
                res_resp = "{}x{}".format(width, height).encode('utf-8')

                fr_resp = float(camera.framerate)

                ex_resp = "{}".format(camera.exposure_mode)

                sh_resp = float(camera.shutter_speed)

                sensor_message["im"] = last_image
                sensor_message["fr"] = fr_resp
                sensor_message["res"] = res_resp
                sensor_message["exp"] = ex_resp
                sensor_message["shu"] = sh_resp

                sensor_message['ty'] = "camera"

                binary_packet = msgpack.packb(sensor_message, use_bin_type = True)

                if rfm69_enabled:
                    logger.debug("sending camera packet to radio")

                    try:
                        radio_queue.put(binary_packet)
                    except Full:
                        logger.debug("radio queue full")

                if awsiot_enabled:
                    logger.debug("sending camera packet to aws")

                    try:
                        awsiot_queue.put(binary_packet)
                    except Full:
                        logger.debug("aws queue full")

                if mqtt_enabled:
                    logger.debug("sending camera packet to mqtt")

                    try:
                        mqtt_queue.put(binary_packet)
                    except Full:
                        logger.debug("mqtt queue full")

                if websocket_enabled:
                    logger.debug("sending camera packet to websocket")

                    try:
                        websocket_queue.send(binary_packet)
                    except Full:
                        logger.debug("websocket queue full")
        finally:
            pass

if __name__ == "__main__":
    if web_enabled:
        logger.info('Publishing mDNS service...')
        zeroconf = Zeroconf()
        host = platform.node()

        ip = get_local_ip()
        logger.info("Local IP: %s", ip)

        desc = {}
        info = ServiceInfo(type_ = "_http._tcp.local.",
                           name = host + "._http._tcp.local.",
                           address = socket.inet_aton(ip),
                           port = port,
                           properties = desc)

        logger.info("Registering mDNS: %s", info)

    try:
        loop = asyncio.get_event_loop()

        if camera_enabled:
            camera_thread = Thread(target = camera_loop, name = "camera_thread")
            camera_thread.start()

        if websocket_enabled:
            websocket_thread = Thread(target = _websocket_loop, name = "websocket_thread")
            websocket_thread.start()

        if web_enabled:
            zeroconf.register_service(info)
            web_task = loop.create_task(web_loop())

        if rfm69_enabled:
            radio_thread = Thread(target = radio_loop, name = "radio_thread")
            radio_thread.start()

        if awsiot_enabled:
            awsiot_thread = Thread(target = awsiot_loop, name = "awsiot_thread")
            awsiot_thread.start()

        if mqtt_enabled:
            mqtt_thread = Thread(target = mqtt_loop, name = "mqtt_thread")
            mqtt_thread.start()


        sensor_thread = Thread(target = _sensor_loop, name = "sensor_thread")
        sensor_thread.start()

        loop.run_forever()

    except Exception:
        logger.exception("Exception occurred during loop")
    finally:
        if camera_enabled:
            camera_shutdown = True

        if rfm69_enabled:
            # try to ensure everything gets reset
            radio_shutdown = True

        if mqtt_enabled:
            mqtt_shutdown = True

        if awsiot_enabled:
            awsiot_shutdown = True
        
        if websocket_enabled:
            websocket_shutdown = True

        if web_enabled:
            logger.info("Removing mDNS service...")
            zeroconf.unregister_service(info)
            zeroconf.close()
