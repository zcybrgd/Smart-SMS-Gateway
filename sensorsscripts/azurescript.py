import adafruit_dht
import board
import time
import os
import json
import paho.mqtt.client as mqtt
from azure.iot.device import IoTHubDeviceClient, Message


MQTT_BROKER = "127.0.0.1" 
MQTT_PORT = 1883
MQTT_TOPIC_TEMP = "home/temperature"
MQTT_TOPIC_HUMIDITY = "home/humidity"
MQTT_CLIENT_ID = "raspberry_dht22"

dht_device = adafruit_dht.DHT22(board.D4)

CONNECTION_STRING = os.getenv("AZURE_IOT_HUB_CONNECTION_STRING")

azure_client = IoTHubDeviceClient.create_from_connection_string(CONNECTION_STRING)

mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
    else:
        print(f"Connection failed with code {rc}")

mqtt_client.on_connect = on_connect

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()

    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity

            if temperature is not None and humidity is not None:
                print(f"Temp: {temperature:.1f}°C, Humidity: {humidity:.1f}%")

                mqtt_client.publish(MQTT_TOPIC_TEMP, f"{temperature:.1f}")
                mqtt_client.publish(MQTT_TOPIC_HUMIDITY, f"{humidity:.1f}")
                #send dqtq to azure
                data = {
                    "temperature": temperature,
                    "humidity": humidity
                }
                msg = Message(json.dumps(data))
                azure_client.send_message(msg)
                print("Data sent to Azure IoT Hub.")

            else:
                print("Failed to retrieve data from sensor.")

        except RuntimeError as e:
            print(f"Sensor error: {e}. Retrying...")
            time.sleep(2)

        except OSError as e:
            print(f"OS error: {e}. Restarting sensor...")
            dht_device.exit()
            time.sleep(2)
            dht_device = adafruit_dht.DHT22(board.D4)

        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(10)

except KeyboardInterrupt:
    print("Exiting...")

finally:
    print("Cleaning up...")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()
    azure_client.shutdown()
    dht_device.exit()
