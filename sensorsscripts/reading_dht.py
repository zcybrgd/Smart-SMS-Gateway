import adafruit_dht
import board
import time
import paho.mqtt.client as mqtt

# MQTT Broker Configuration
MQTT_BROKER = "127.0.0.1"  
MQTT_PORT = 1883 
MQTT_TOPIC = "home/temperature"  # Topic to publish temperature data
MQTT_TOPIC_HUMIDITY = "home/humidity"  # Topic to publish humidity data
MQTT_CLIENT_ID = "raspberry_dht22"  # Unique client ID

# DHT22 Sensor Configuration
dht_device = adafruit_dht.DHT22(board.D4)  # Use GPIO4 (Pin 7)

# MQTT Client Setup
client = mqtt.Client(client_id=MQTT_CLIENT_ID, callback_api_version=mqtt.CallbackAPIVersion.VERSION1)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT broker")
    else:
        print(f"Connection to MQTT broker failed with code {rc}")

client.on_connect = on_connect

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)  # 60 is the keepalive interval
    client.loop_start()  # Start the MQTT loop

    while True:
        try:
            temperature = dht_device.temperature
            humidity = dht_device.humidity

            if temperature is not None and humidity is not None:
                print(f"Temp: {temperature:.1f}°C, Humidity: {humidity:.1f}%")
                client.publish(MQTT_TOPIC, f"{temperature:.1f}")  # Publish temperature
                client.publish(MQTT_TOPIC_HUMIDITY, f"{humidity:.1f}")  # Publish humidity
            else:
                print("Failed to retrieve data from DHT22 sensor")

        except RuntimeError as e:
            print(f"Error reading sensor: {e}. Retrying...")
            time.sleep(2)  # Give the sensor some time before retrying

        except OSError as e:
            print(f"OS error with sensor: {e}. Restarting sensor...")
            dht_device.exit()
            time.sleep(2)
            dht_device = adafruit_dht.DHT22(board.D4) 

        except Exception as e:
            print(f"Unexpected error: {e}")

        time.sleep(10)  
except KeyboardInterrupt:
    print("Exiting...")

except Exception as e:
    print(f"Critical error: {e}")

finally:
    print("Cleaning up...")
    client.loop_stop() 
    client.disconnect()
    dht_device.exit()
