with open("identity.txt","r") as f:
    identity = f.read().strip()
import json
with open(f"/branches/{identity}/config.json","r") as j:
    config = json.load(j)
with open("wifi.json","r") as j:
    wifi_config = json.load(j)
with open("mqtt.json","r") as j:
    mqtt_config = json.load(j)
with open("log_override.json","r") as j:
    log_config = json.load(j)
with open("version.ver","r") as f:
    version = f.read().strip()
print("Version:",version)
print("Identity:",identity)
update_log = ""
config["SETTINGS"].update(log_config)
config["WIFI"].update(wifi_config)
config["MQTT"].update(mqtt_config)
import os
try:
    os.stat("update_flag.txt")
    print("Updating...")
    import pull
    update_log = "[UPDATE]"+pull.update(config["WIFI"])
except OSError:
    pass



import time
import ssl
import gc
from machine import Pin, Timer, reset, WDT
from umqtt.robust import MQTTClient


TOPIC_CHECK_I = b'check'
TOPIC_CHECK_O = b'status'
TOPIC_DATA_O = b'data'
TOPIC_CONTROL_I = b'control'
TOPIC_DATA_I = b'give'
TOPIC_LOG_O = b'log'
TOPIC_UPDATE_I = b'update'
TOPIC_RESET_I = b'reset'
name_base = config["MQTT"]["ID"]
TOPIC_LOG_I = bytes(name_base+"/log_override","utf-8")
TOPIC_I = [TOPIC_CHECK_I, TOPIC_CONTROL_I, TOPIC_DATA_I, TOPIC_LOG_I, TOPIC_UPDATE_I, TOPIC_RESET_I]

check_recieved = False
class Logger:
    def __init__(self,log_count_mqtt=False,log_send_ram=False,log_send_print=False,log_send_time=False):
        self.log_count_mqtt = log_count_mqtt
        self.log_send_ram = log_send_ram
        self.log_send_print = log_send_print
        self.log_send_time = log_send_time
        self.count_in = 0
        self.count_out = 0
        self.print_buffer = []
    def increment_in(self):
        self.count_in += 1
    def increment_out(self):
        self.count_out += 1
    def print(self,*args, end="\n"):
        print(*args, end=end)
        if self.log_send_print:
            for a in args:
                self.print_buffer.append(str(a))

    def read_ram_tuple(self):
        gc.collect()
        alloc = gc.mem_alloc()
        free = gc.mem_free()
        whole = alloc + free
        return alloc,free,whole,round(alloc/whole,4)
    def read_ram(self):
        gc.collect()
        alloc = gc.mem_alloc()
        free = gc.mem_free()
        whole = alloc + free
        return f"Allocated: {alloc}, Free: {free}, Total: {whole}, Usage: {round(alloc/whole*100,2)}%"
    def prepare_log(self):
        msg = f"[LOG] {config["MQTT"]["ID"]} [VERSION] {version}\n"
        if self.log_send_time:
            import ntptime
            ntptime.settime()
            msg += f"[TIME] {time.localtime()}\n"
        if self.log_count_mqtt:
            msg += f"[MQTT COUNT] IN: {str(self.count_in)} OUT: {str(self.count_out)}\n"
        if self.log_send_ram:
            ram = self.read_ram()
            msg += f"[RAM] {str(ram)}\n"
        if self.log_send_print:
            msg += "[PRINT]\n"
            for line in self.print_buffer:
                msg += str(line) + "\n"
            self.print_buffer = []
            msg += "[END PRINT]\n"
        return msg 
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
        from ds18x20 import DS18X20
        from machine import Pin
        from onewire import OneWire
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
    def _report(self):
        printl("Reporting temperature for",self.name)
        logger.increment_out()
        client.publish(self.name,str(self.get_temp()))
        wdt.feed()
        time.sleep(2)
    def _command(self,msg):
        pass
class Bme280:
    def __init__(self, sda, scl,name):
        from bme280_float import BME280
        from machine import Pin, SoftI2C
        self.name = name
        self.sda = Pin(sda)
        self.scl = Pin(scl)
        self.sensor = BME280(i2c=SoftI2C(sda=sda, scl=scl))
    def get_data(self):
        temp,press,hum = self.sensor.read_compensated_data()
        dew = self.sensor.dew_point
        return temp,press,hum,dew
    def _report(self):
        wdt.feed()
        data = self.get_data()
        printl("Reporting BME280 data for",self.name,": Temperature")
        logger.increment_out()
        client.publish(self.name+"/teplota",str(data[0]))
        time.sleep(2)
        printl("Reporting BME280 data for",self.name,": Pressure")
        logger.increment_out()
        client.publish(self.name+"/tlak",str(data[1]))
        wdt.feed()
        time.sleep(2)
        printl("Reporting BME280 data for",self.name,": Humidity")
        logger.increment_out()
        client.publish(self.name+"/vlhkost",str(data[2]))
        wdt.feed()
        time.sleep(2)
        printl("Reporting BME280 data for",self.name,": Dew Point")
        logger.increment_out()
        client.publish(self.name+"/rosny_bod",str(data[3]))
        wdt.feed()
        time.sleep(2)
    def _command(self, msg):
        pass
class Rele:
    def __init__(self, pin,name,inverted=False):
        self.pin = Pin(pin,mode=Pin.OUT,pull=Pin.PULL_DOWN,value=0)
        self.name = name
        self.state = 0
        self.inverted = inverted
    def get(self):
        return self.state
    def set(self,state):
        if not self.inverted:
            self.pin.value(bool(state))
        else:
            self.pin.value(not state)
        self.state = state
    def _report(self):
        printl("Reporting state for",self.name)
        logger.increment_out()
        client.publish(self.name,str(self.get()))
        wdt.feed()
        time.sleep(2)
    def _command(self, msg):
        if str(self.name)+"0" in msg:
            self.set(0)
        if str(self.name)+"1" in msg:
            self.set(1)
class Button:
    def __init__(self, pin,name,inverted=False):
        self.pin = Pin(pin,mode=Pin.IN)
        self.name = name
        self.inverted = inverted
    def get(self):
        if self.inverted:
            return not self.pin.value()
        return bool(self.pin.value())
    def _report(self):
        printl("Reporting state for",self.name)
        logger.increment_out()
        client.publish(self.name,str(self.get()))
        wdt.feed()
        time.sleep(2)
    def _command(self, msg):
        pass
class KIT:
    def __init__(self,pins,name):
        from rotary import Rotary
        from machine import Pin, PWM
        from lcd import LiquidCrystal
        self.name = name
        self.rt = Rotary(*pins[0:3], press=self._rtbtn,clockwise=self._rtrotate,
                         counterclockwise=self._rtrotate,snapRotation=True)
        self.lcd = LiquidCrystal(*pins[3:9])
        self.kill = Pin(pins[9], Pin.IN, Pin.PULL_UP)
        self.kill.irq(trigger=Pin.IRQ_FALLING, handler=lambda pin: self._killbtn())
        self.buzzer = PWM(Pin(pins[10]), freq=440, duty_u16=0)
        self.lcd.begin(20,4)
        self.lcd.setCursor(0,0)
        self.data = []
        self.lcd.print("KIT Initialized")
    def _rtbtn(self):
        if hasattr(self, 'init'):
            printl("Rotary button pressed")
    def _killbtn(self):
        if hasattr(self, 'init'):
            printl("Kill button pressed")   
            client.publish("reset","ALL")
    def _rtrotate(self):
        if hasattr(self, 'init'):
            printl("Rotary rotated")
            self.update_lcd()
    def update_lcd(self):
        index = self.rt.get_value() % 15
        if index == 0:
            strings = ["Kotel","Rele","Zapnuto" if self.data[index] == "on" else "Vypnuto",""]
        elif index == 1:
            strings = ["Kotel","Ventil","Boiler" if self.data[index] == "on" else "Topení",""]
        elif index == 2:
            strings = ["Kotel","Boiler",self.data[index]+"°C",""]
        elif index == 3:
            strings = ["Kotel","Vstup",self.data[index]+"°C",""]
        elif index == 4:
            strings = ["Kotel","Vystup",self.data[index]+"°C",""]
        elif index == 5:
            strings = ["Obyvak","Teplota",self.data[index]+"°C",""]
        elif index == 6:
            strings = ["Obyvak","Vlhkost",self.data[index]+"%",""]
        elif index == 7:
            strings = ["Obyvak","Tlak",self.data[index]+"kPa",""]
        elif index == 8:
            strings = ["Obyvak","Rosny bod",self.data[index]+"°C",""]
        elif index == 9:
            strings = ["Koupelna","Teplota",self.data[index]+"°C",""]
        elif index == 10:
            strings = ["Koupelna","Vlhkost",self.data[index]+"%",""]
        elif index == 11:
            strings = ["Koupelna","Tlak",self.data[index]+"kPa",""]
        elif index == 12:
            strings = ["Koupelna","Rosny bod",self.data[index]+"°C",""]
        elif index == 13:
            strings = ["Borek","Rele","Zapnuto" if self.data[index] == "on" else "Vypnuto",""]
        elif index == 14:
            strings = ["Mirosov","SG",("1" if self.data[index+1] == "on" else "0")+("1" if self.data[index] == "on" else "0"),""]

        self.lcd.clear()
        self.lcd.setCursor(0,0)
        self.lcd.print(strings[0])
        self.lcd.setCursor(1,0)
        self.lcd.print(strings[1])
        self.lcd.setCursor(2,0)
        self.lcd.print(str(strings[2]))
        self.lcd.setCursor(3,0)
        self.lcd.print(strings[3])

    def get(self):
        return ""
    
    def buzz(self):
        self.buzzer.duty_u16(32768)
        time.sleep(0.2)
        self.buzzer.duty_u16(0)

    def _report(self):
        printl("Reporting state for",self.name)
        logger.increment_out()
        client.publish(self.name,str(self.get()))
        self.init = True
        wdt.feed()
        time.sleep(2)
    def _command(self, msg):
        if str(self.name)+"/buzz" in msg:
            self.buzz()
        if str(self.name)+"/data:" in msg:
            data = msg.split("|")[1:]
            printl("KIT received raw data:",data)
            self.data = []
            for d in data:
                self.data.append(d)
            printl("KIT received data:",self.data)
            self.update_lcd()
            

logger = Logger(
    log_count_mqtt=config["SETTINGS"]["LOG_COUNT_MQTT"],
    log_send_ram=config["SETTINGS"]["LOG_SEND_RAM"],
    log_send_print=config["SETTINGS"]["LOG_SEND_PRINT"],
    log_send_time=config["SETTINGS"]["LOG_SEND_TIME"]
)
printl = logger.print    
printl("Logger initialized")

peripherals = []
name_base = config["MQTT"]["ID"]
kit = None
for p in config["PERIPHERALS"]:
    if p["TYPE"]=="RELE":
        peripherals.append(Rele(p["PIN"],name_base+"/"+p["NAME"],p["INVERTED"]))
    if p["TYPE"]=="BME":
        peripherals.append(Bme280(p["SDA_PIN"],p["SCL_PIN"],name_base+"/"+p["NAME"]))
    if p["TYPE"]=="DHT":
        peripherals.append(Sonda(p["PIN"],name_base+"/"+p["NAME"]))
    if p["TYPE"]=="BUTTON":
        peripherals.append(Button(p["PIN"],name_base+"/"+p["NAME"],p["INVERTED"]))
    if p["TYPE"]=="TESTING":
        kit = KIT(p["PINS"],name_base+"/"+p["NAME"])
        peripherals.append(kit)



printl(f"Initialized {len(peripherals)} peripherals: {[p.name for p in peripherals]}")
# Connect to strongest known Wi-Fi
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

# Respond to CHECK message
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
    try:
        for p in peripherals:
            wdt.feed()
            p._report()
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
    elif topic == TOPIC_CONTROL_I:
        for p in peripherals:
            p._command(msg.decode())
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



# Main loop
def mqtt_loop():
    try:
        wdt.feed()
        led.on()
        connect_best_wifi()
        connect_mqtt()
        # Start periodic button state reporting
        timer = Timer()
        timer.init(period=config["SETTINGS"]["PERIODIC_SEND_S"], mode=Timer.PERIODIC, callback=report_state)
        report_state(timer)
        wdt.feed()
        led.off()
        active_timer = Timer()
        active_timer.init(period=600_000, mode=Timer.PERIODIC, callback=timout_callback)
        printl("Entering main loop")
        while True:
            try:
                wdt.feed()
                printl("Checking for MQTT message...")
                client.check_msg()
                gc.collect()
                wdt.feed()
                time.sleep(3)
            except Exception as e:
                printl("MQTT error during loop:", e)
                wdt.feed()
                time.sleep(5)
                wdt.feed()
                connect_mqtt()  # Reconnect on failure

    except Exception as e:
        printl("Startup error:", e)
    finally:
        try:
            client.disconnect()
            printl("Disconnected from MQTT")
        except:
            pass

def timout_callback(t):
    global check_recieved
    if not check_recieved:
        printl("No CHECK received in 10 minutes, resetting")
        reset()
    check_recieved = False    

printl("starting")
printl(config["MQTT"]["ID"])
led = StatusLight()
led.on()
time.sleep(1)
led.off()
printl("Waiting for keyboard interupt")
time.sleep(4)
printl("Initializing WDT")
wdt = FakeWDT()
if config["SETTINGS"]["USE_WDT"]:
    printl("real WDT enabled")
    wdt = WDT(timeout=config["SETTINGS"]["WDT_TIMEOUT"])
mqtt_loop()
printl("reseting")
time.sleep(5)
reset()