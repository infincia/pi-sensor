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

**Note:** There is nothing in this script that retrieves or displays the sensor values,
this is just the Pi sensor node component. 

#### Planned features

* Single configuration file for all common settings/credentials
* Actions linked to MQTT topics, to allow things like remote reboot of the Pi sensor node
* Freezing point / Condensation warnings published to an MQTT topic

#### Usage

To use this code, clone the repo to `/opt/pi-sensor`:

    git clone https://github.com/steveatinfincia/pi-sensor.git

Then register a new device in the AWS IoT dashboard, using the Linux + Python SDK selection,
and **name it according to the hostname of your Pi**. The code currently uses the hostname for 
MQTT topics, and for the filenames of the AWS IoT credential files. This will change soon, but
for now make things easy and use the same name for the Pi hostname and the AWS IoT device name.

AWS IoT dashboard will then download a `connect_device_package.zip` archive, put this archive
in `/etc/aws/` on your pi and unzip it:

    mkdir /etc/aws
    mv path/to/connect_device_package.zip /etc/aws/
    cd /etc/aws
    unzip connect_device_package.zip

You will then need to run the `start.sh` script provided by AWS IoT so that it can install
the Python SDK and retrieve the AWS IoT root CA certificate:

    /bin/bash /etc/aws/start.sh

You will need to edit the endpoint in `sensor.py` so that it matches the one
listed in your AWS account's IoT dashboard -> Settings area. This will change soon
but for now it is hardcoded.

You will also need to install the Python dependencies for the Si7021 sensor, if you are using
one:

    pip install Adafruit-PureIO

Then you can enable the systemd unit:

    systemctl enable /opt/pi-sensor/sensor.service

And now start it:

    systemctl start sensor

Feel free to open an issue on Github if something doesn't work right :)
