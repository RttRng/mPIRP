from irv_lib import *
wdt = FakeWDT()
try:
    # This fill throw exception if run from terminal
    if(isinstance(logger,Logger)):
        pass
    else:
        raise Exception("not declared in boot")
except:
    # Enable messages in terminal
    logger = Logger(True)



identity = get_id()
config = read_json(f"/branches/{identity}/config.json")
wifi_config = read_json("wifi.json")
mqtt_config = read_json("mqtt.json")
log_config = read_json("log_override.json")
version = read_json("version.json")
logger.print("Version:",version["version"],"" if version["tested"] else ",untested","" if version["stable"] else ",unstable")
logger.print("Identity:",identity)
config["SETTINGS"].update(log_config)
config["WIFI"].update(wifi_config)
config["MQTT"].update(mqtt_config)

logger.print("Initializing WDT")
wdt = FakeWDT()
if config["SETTINGS"]["USE_WDT"] and not logger.debug:
    logger.print("real WDT enabled")
    wdt = WDT(timeout=config["SETTINGS"]["WDT_TIMEOUT"])



TOPIC_CHECK_I = b'check'
TOPIC_CHECK_O = b'status'
TOPIC_CONTROL_I = b'control'
TOPIC_DATA_I = b'give'
TOPIC_LOG_O = b'log'
TOPIC_UPDATE_I = b'update'
TOPIC_RESET_I = b'reset'
TOPIC_CONTROL_I_LIST = []
name_base = config["MQTT"]["ID"]
TOPIC_REPORT_O = name_base
TOPIC_LOG_I = bytes(name_base+"/log_override","utf-8")
TOPIC_I = [TOPIC_CHECK_I, TOPIC_CONTROL_I, TOPIC_DATA_I, TOPIC_LOG_I, TOPIC_UPDATE_I, TOPIC_RESET_I]

check_recieved = False









peripherals = []
name_base = config["MQTT"]["ID"]
for p in config["PERIPHERALS"]:
    if p["TYPE"]=="RELE":
        peripherals.append(Rele(p["PIN"],name_base+"/"+p["NAME"],p["INVERTED"]))
    if p["TYPE"]=="BME":
        peripherals.append(Bme280(p["SDA_PIN"],p["SCL_PIN"],name_base+"/"+p["NAME"]))
    if p["TYPE"]=="DHT":
        peripherals.append(Sonda(p["PIN"],name_base+"/"+p["NAME"]))
    if p["TYPE"]=="BUTTON":
        peripherals.append(Ventil(p["PIN"],name_base+"/"+p["NAME"],p["INVERTED"]))


logger.print(f"Initialized {len(peripherals)} peripherals: {[p.name for p in peripherals]}")



# Main loop
def mqtt_loop():
#     try:
#         wdt.feed()
#         led.on()
#         TOPIC_I.extend(TOPIC_CONTROL_I_LIST)
#         connect_best_wifi()
#         connect_mqtt()
#         # Start periodic button state reporting
#         timer = Timer()
#         timer.init(period=config["SETTINGS"]["PERIODIC_SEND_S"], mode=Timer.PERIODIC, callback=report_state)
#         report_state(timer)
#         wdt.feed()
#         led.off()
#         active_timer = Timer()
#         active_timer.init(period=600_000, mode=Timer.PERIODIC, callback=timout_callback)
#         printl("Entering main loop")
#         while True:
#             try:
#                 wdt.feed()
#                 printl("Checking for MQTT message...")
#                 client.check_msg()
#                 gc.collect()
#                 wdt.feed()
#                 time.sleep(3)
#             except Exception as e:
#                 printl("MQTT error during loop:", e)
#                 wdt.feed()
#                 time.sleep(5)
#                 wdt.feed()
#                 connect_mqtt()  # Reconnect on failure

#     except Exception as e:
#         printl("Startup error:", e)
#     finally:
#         try:
#             client.disconnect()
#             printl("Disconnected from MQTT")
#         except:
#             pass

def timout_callback(t):
#     global check_recieved
#     if not check_recieved:
#         printl("No CHECK received in 10 minutes, resetting")
#         reset()
#     check_recieved = False    

printl("starting")
printl(config["MQTT"]["ID"])

time.sleep(1)
led.off()
printl("Waiting for keyboard interupt")
time.sleep(4)

mqtt_loop()
printl("reseting")
time.sleep(5)
reset()