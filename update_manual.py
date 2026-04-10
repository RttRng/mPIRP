import json
with open("wifi.json","r") as j:
    wifi_config = json.load(j)
import pull
print(pull.update(wifi_config))