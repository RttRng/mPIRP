def update(credentials):
    try:
        connect_best_wifi(credentials)
        import urequests
        with open("api.key", "r") as f:
            key = f.read().strip()
        with open("base_url.txt", "r") as f:
            base_url = f.read().strip()
        url = base_url+"manifest.json"
        headers = {"X-API-KEY": key}
        response = urequests.get(url, headers=headers)
        manifest = {}
        if response.status_code == 200:
            manifest = response.json()
            print("Manifest fetched!")
        else:
            print("Failed to fetch manifest:", response.status_code)
            response.close()
            return "Failed to fetch manifest: " + str(response.status_code)
        response.close()
        print("Manifest:", manifest)
        import os
        dirs = manifest["dirs"]
        for dir in dirs:
            try:
                os.mkdir(dir)
            except OSError as e:
                if e.args[0] == 17:  # EEXIST
                    pass
                else:
                    print("Failed to create directory:", dir, e)
                    return "Failed to create directory: " + dir
        for file_info in manifest["files"]:
            name = file_info["name"]
            path = file_info["path"]
            print("Downloading", name, "to", "/"+path) 
            resp = urequests.get(base_url+path+name, headers=headers)
            if resp.status_code != 200:
                print("Failed to download file:", name, resp.status_code)
                resp.close()
                return "Failed to download file: " + name + " " + str(resp.status_code)
            with open("/"+path+name, "w") as f:
                f.write(resp.content)
            resp.close()
        try:
            os.remove("update_flag.txt")
        except OSError:
            pass
        print("Update completed successfully!")
        import machine
        machine.reset()
    except Exception as e:
        print("Update failed:", e)
        return "Update failed: " + str(e)



def connect_best_wifi(credentials):
    max_attempts = 5
    import network
    from time import sleep
    wlan = network.WLAN(network.STA_IF)
    try:
        wlan.deinit()
    except:
        print("Wi-Fi deinit failed")
    wlan.active(True)
    for attempt in range(max_attempts):
        print(f"Wi-Fi scan attempt {attempt + 1}")
        nets = wlan.scan()
        best_net = None
        best_rssi = -999
        for ssid_bytes, _, _, rssi, _, _ in nets:
            ssid = ssid_bytes.decode()
            if ssid in credentials and rssi > best_rssi:
                best_net = ssid
                best_rssi = rssi
        if best_net:
            print(f"Connecting to: {best_net} (RSSI: {best_rssi})")
            wlan.connect(best_net, credentials[best_net])
            timeout = 15
            while not wlan.isconnected() and timeout > 0:
                print(".", end="")
                sleep(1)
                timeout -= 1
            if wlan.isconnected():
                print("\nConnected to Wi-Fi!")
                print("IP:"+str(wlan.ifconfig()[0]))
                return True
            else:
                print("Wi-Fi connection timed out")
        else:
            print("No known networks found")
        sleep(1)
    raise Exception("Failed to connect to Wi-Fi after multiple attempts")
