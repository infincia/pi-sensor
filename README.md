### Raspberry Pi Temperature/Humidity Sensor for AWS IoT

This is a simple Python script that checks local disk, ram, and CPU usage, and
publishes each one to a separate MQTT topic based on the hostname of the Pi.

If your pi has a hostname 'pi-node1', you will get sensor values published to:

    /pi-node1/ram
    /pi-node1/cpu
    /pi-node1/disk

Additionally, you can optionally connect an Si7021 temperature/humidity sensor 
to the GPIO pins (3v, ground, SDA, SCL), which will publish to the following MQTT
topics:

    /pi-node1/temperature
    /pi-node1/humidity

Temperature value is fahrenheit as a decimal number, humidity is the percentage
as a decimal number. Celcius is returned from the sensor, so if you would rather
publish that instead, the script can be edited very easily.

Leaving the sensor disconnected will not break anything else, the other values
should still be published to AWS IoT.

#### Planned features

* Single configuration file for all common settings/credentials
* Actions linked to MQTT topics, to allow things like remote reboot of the Pi sensor node
* Freezing point / Condensation warnings published to an MQTT topic

#### Usage

To use this code, clone the repo to `/opt/pi-sensor` and put your AWS IoT
certificate credentials in `/etc/aws`. These are the same files that you get
by downloading the `connect_device_package.zip` archive when onboarding from AWS
IoT dashboard.

You will need to edit the endpoint in `sensor.py` so that it matches the one
listed in your AWS account's IoT dashboard -> Settings area.

You will also need to install the Python dependencies. Only PureIO is
available via pip, the AWS IoT library must be cloned and installed manually:

    pip install Adafruit-PureIO

    git clone https://github.com/aws/aws-iot-device-sdk-python.git
    cd aws-iot-device-sdk-python
    sudo python setup.py install


Then you can enable the systemd unit:

    systemctl enable /opt/pi-sensor/sensor.service

And now start it:

    systemctl start /opt/pi-sensor/sensor.service


