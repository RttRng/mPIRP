import os
import time
import ssl
import gc
from machine import Pin, Timer, reset, WDT, SoftI2C
from umqtt.robust import MQTTClient
from bme280_float import BME280
from ds18x20 import DS18X20
from onewire import OneWire
import json
class Logger:
    def __init__(self,debug:bool) -> None:
        self.debug = debug
        self.count_in = 0
        self.count_out = 0
    def setDebug(self,state:bool):
        self.debug = state
    def increment_in(self):
        self.count_in += 1
    def increment_out(self):
        self.count_out += 1
    def print(self,*args, end="\n"):
        if self.debug:
            print(*args, end=end)
def read_json(file:str):
    with open(file,"r") as f:
        return json.load(f)
def write_json(file:str,data:str):
    with open(file,"w") as f:
        json.dump(data,f)
def get_id():
    with open("identity.txt","r") as f:
        return f.read().strip()
class FakeWDT:
    def __init__(self, timeout=8000):
        pass
    def feed(self):
        pass
class StatusLight:
    def __init__(self):
        self.led = Pin("LED", Pin.OUT)
    def on(self):
        self.led.on()
    def off(self):
        self.led.off()
    def toggle(self):
        self.led.value(not self.led.value())
class Sonda:
    def __init__(self, pin,name):
        self.name = name
        self.pin = Pin(pin)
        self.sensor = DS18X20(OneWire(self.pin))
        self.roms = self.sensor.scan()
        if len(self.roms)!=1:
            raise Exception("Expected 1 sensor on pin "+str(pin)+", got "+str(len(self.roms)))
    def get_temp(self):
        from time import sleep_ms
        self.sensor.convert_temp()
        sleep_ms(750)
        temp = round(self.sensor.read_temp(self.roms[0]),2)
        return temp
    def report(self):
        printl("Reporting temperature for",self.name)
        return {self.name:str(self.get_temp())}
    def command(self,topic,msg):
        pass
class Bme280:
    def __init__(self, sda, scl,name):
        self.name = name
        self.sda = Pin(sda)
        self.scl = Pin(scl)
        self.sensor = BME280(i2c=SoftI2C(sda=sda, scl=scl))
    def get_data(self):
        temp,press,hum = self.sensor.read_compensated_data()
        dew = self.sensor.dew_point
        return temp,press,hum,dew
    def report(self):
        data = self.get_data()
        printl("Reporting BME280 data for",self.name,": Temperature")
        printl("Reporting BME280 data for",self.name,": Pressure")
        printl("Reporting BME280 data for",self.name,": Humidity")
        printl("Reporting BME280 data for",self.name,": Dew Point")
        return {self.name+"/teplota":str(data[0]),
                self.name+"/tlak":str(data[1]),
                self.name+"/vlhkost":str(data[2]),
                self.name+"/rosny_bod":str(data[3])}
    def command(self, topic, msg):
        pass
class Rele:
    def __init__(self, pin,name,inverted=False):
        self.pin = Pin(pin,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.name = name
        self.state = 0
        self.inverted = inverted
        TOPIC_CONTROL_I_LIST.append('control/'+self.name)
    def get(self):
        return self.state
    def set(self,state):
        printl("Switching "+self.name+" to "+str(state))
        if not self.inverted:
            self.pin.value(bool(state))
        else:
            self.pin.value(not state)
        self.state = state
    def report(self):
        printl("Reporting state for",self.name)
        return {self.name:str(self.get())}
    def command(self, topic, msg):
        if topic == 'control/'+self.name:
            if "false" in msg:
                self.set(0)
            if "true" in msg:
                self.set(1)
class Ventil:
    def __init__(self, pin,name,inverted=False):
        self.pin = Pin(pin,mode=Pin.IN)
        self.name = name
        self.inverted = inverted
    def get(self):
        if self.inverted:
            return not self.pin.value()
        return bool(self.pin.value())
    def report(self):
        printl("Reporting state for",self.name)
        return {self.name:str(self.get())}
    def command(self, topic, msg):
        pass


def connect_best_wifi(max_attempts=5):
    wdt.feed()
    import network
    from time import sleep
    wlan = network.WLAN(network.STA_IF)
    try:
        wlan.deinit()
    except:
        printl("Wi-Fi deinit failed")
    wlan.active(True)
    credentials = config["WIFI"]

    for attempt in range(max_attempts):
        wdt.feed()
        printl(f"Wi-Fi scan attempt {attempt + 1}")
        nets = wlan.scan()
        best_net = None
        best_rssi = -999
        for ssid_bytes, _, _, rssi, _, _ in nets:
            ssid = ssid_bytes.decode()
            if ssid in credentials and rssi > best_rssi:
                best_net = ssid
                best_rssi = rssi
        if best_net:
            printl(f"Connecting to: {best_net} (RSSI: {best_rssi})")
            wlan.connect(best_net, credentials[best_net])
            timeout = 15
            while not wlan.isconnected() and timeout > 0:
                printl(".", end="")
                wdt.feed()
                sleep(1)
                timeout -= 1
            if wlan.isconnected():
                printl("\nConnected to Wi-Fi!")
                printl("IP:"+str(wlan.ifconfig()[0]))
                return True
            else:
                printl("Wi-Fi connection timed out")
        else:
            printl("No known networks found")
        sleep(1)
    raise Exception("Failed to connect to Wi-Fi after multiple attempts")

def respond_status(client):
    msg = str(config["MQTT"]["ID"]).encode()
    try:
        logger.increment_out()
        client.publish(TOPIC_CHECK_O, msg)
        printl(f"Responded to CHECK with: {msg}")
    except Exception as e:
        printl("Failed to publish CHECK response:", e)
# Send state every 5 minutes
def report_state(timer):
    wdt.feed()
    printl("Reporting state...")
    report = {}
    try:
        for p in peripherals:
            wdt.feed()
            report.update(p.report())
        printl(json.dumps(report))
        client.publish(TOPIC_REPORT_O,json.dumps(report))
    except Exception as e:
        printl("Failed to publish state:", e)
    wdt.feed()
    try:
        msg = logger.prepare_log()
        if msg!="":
            logger.increment_out()
            client.publish(TOPIC_LOG_O,msg)
            printl("Sent log")
    except Exception as e:
        printl("Failed to publish log:", e)
            
# Callback for received messages
def sub_cb(topic, msg):
    logger.increment_in()
    msg_me = msg == identity.encode() or msg == b'' or msg == b'ALL'
    printl("Message for me:",msg_me)
    printl(f"Received message on {topic}: {msg}")
    if topic == TOPIC_CHECK_I and msg_me:
        global check_recieved
        check_recieved = True
        respond_status(client)
    elif topic == TOPIC_DATA_I and msg_me:
        report_state(None)
    elif topic == TOPIC_LOG_I:
        try:
            new_settings = json.loads(msg)
            # Save updated settings to file
            with open("log_override.json", "w") as j:
                json.dump(new_settings, j)
            reset()  # Restart to apply new settings
        except Exception as e:
            printl("Failed to update log settings:", e)
    elif topic == TOPIC_UPDATE_I and msg_me:
        with open("update_flag.txt","w") as f:
            f.write("1")
            reset()
    elif topic == TOPIC_RESET_I and msg_me:
        reset()
    else:
        for p in peripherals:
            p.command(topic.decode(),msg.decode())


# MQTT connection with retry
def connect_mqtt(max_attempts=5):
    wdt.feed()
    global client
    for attempt in range(max_attempts):
        wdt.feed()
        try:
            client = MQTTClient(
                config["MQTT"]["ID"],
                config["MQTT"]["BROKER"],
                port=config["MQTT"]["PORT"],
                user=config["MQTT"]["USERNAME"],
                password=config["MQTT"]["PASSWORD"],
                ssl=ssl
            )
            client.set_callback(sub_cb)
            client.connect()
            wdt.feed()
            printl("Connected to HiveMQ Cloud")
            for topic in TOPIC_I:
                client.subscribe(topic)
                printl("Subscribed to",topic)
                client.check_msg()
            wdt.feed()
            return True
        except Exception as e:
            printl(f"MQTT connection failed (attempt {attempt + 1}):", e)
            time.sleep(2)

    raise Exception("Failed to connect to MQTT after multiple attempts")
