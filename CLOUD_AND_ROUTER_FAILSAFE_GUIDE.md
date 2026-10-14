# OFFICIALUM1 — Cloud & Router Complete Fail-Safe Guide
> **Permanent Disaster-Recovery & Fail-Safe Document**  
> *Saved locally at `c:\Users\Abc\Desktop\firwallum1\CLOUD_AND_ROUTER_FAILSAFE_GUIDE.md`*  
> *Even if power cuts (light issue), everything is recorded here step-by-step.*

---

## 1. GitHub Repository (LIVE & PUSHED)

Your private repository has been created and synced with the latest production code:

* **Repository URL:** [https://github.com/officialumsmcllc/firwallum1](https://github.com/officialumsmcllc/firwallum1)
* **Visibility:** `Private`
* **Account:** `officialumsmcllc`
* **Branch:** `main`
* **Docker Ready:** Includes `Dockerfile`, `render.yaml`, `requirements.txt`, and RFC 8484 DoH endpoint (`/dns-query`).

---

## 2. Render Cloud 1-Click Deployment ($1,000 Credit)

Follow these steps to launch the cloud engine 24/7 on Render:

1. Go to [https://dashboard.render.com](https://dashboard.render.com) and log in.
2. Click **New +** ➔ **Web Service**.
3. Select your GitHub repository: **`officialumsmcllc/firwallum1`**.
4. Render will auto-detect configuration from `render.yaml` and `Dockerfile`:
   * **Name:** `officialum1-hub` (or your choice)
   * **Runtime:** `Docker`
   * **Instance Type:** `Starter` ($7/mo) or `Standard` ($25/mo) — *Deducted from your $1,000 credit*
5. Click **Create Web Service**.
6. Wait ~2 minutes for the Docker build to finish.
7. Render will provide your permanent public HTTPS URL, for example:  
   👉 **`https://officialum1-hub.onrender.com`**

> **Your Cloud Firewall Endpoints:**
> * **Web Management Dashboard:** `https://officialum1-hub.onrender.com/`
> * **DNS-over-HTTPS (DoH) Endpoint:** `https://officialum1-hub.onrender.com/dns-query`
> * **Smart PAC Script:** `https://officialum1-hub.onrender.com/proxy.pac`

---

## 3. Cloudflare Zero Trust (Anycast IPv4 Bridge)

To connect the home Huawei router without needing a PC, Cloudflare acts as the IPv4-to-DoH bridge:

1. Open [https://one.dash.cloudflare.com](https://one.dash.cloudflare.com) and sign in.
2. In the left navigation, go to **`Gateway`** ➔ **`DNS Locations`**.
3. Click **`Add a location`**:
   * **Location Name:** `Huawei Home Wi-Fi`
   * **Network / IP:** Cloudflare will auto-detect your current public IP. Check the box to confirm.
4. Click **Done / Save**.
5. Cloudflare will display **2 Dedicated Anycast IPv4 Addresses**:
   * **Primary Anycast DNS:** `172.64.36.1` *(Example — copy your exact IP from Cloudflare)*
   * **Secondary Anycast DNS:** `172.64.36.2` *(Example — copy your exact IP from Cloudflare)*
6. In Cloudflare Zero Trust, go to **`Gateway`** ➔ **`Resolver Policies`**:
   * Set the **Custom Resolver / Upstream** to:  
     👉 **`https://officialum1-hub.onrender.com/dns-query`**

---

## 4. Huawei HG8245C Home Router Setup

Now point the entire home network to Cloudflare's Anycast IPs:

1. Open your browser and navigate to: **`http://192.168.100.1`**
2. Log in with telecom credentials:
   * **Account:** `telecomadmin`
   * **Password:** `admintelecom`
3. Click on the **`LAN`** tab at the top.
4. Select **`DHCP Server Configuration`** from the left sidebar:
   * **Primary DNS Server:** Paste Cloudflare Primary IP (e.g. `172.64.36.1`)
   * **Secondary DNS Server:** Paste Cloudflare Secondary IP (e.g. `172.64.36.2`) or `8.8.8.8` (Google fail-safe)
5. Click **Apply**.
6. *(Optional WAN Hard Lock)* Go to **`WAN`** tab ➔ Click your active internet connection (PPPoE) ➔ Uncheck "Obtain DNS automatically" ➔ Enter the same two Cloudflare IPs ➔ **Apply**.

---

## 5. What Happens During Light Outages (Fail-Safe Protocol)

| Event | System Behavior | Action Required |
|---|---|---|
| **Light cuts (PC turns off)** | Cloudflare + Render are hosted in Tier-4 datacenters (USA/EU) and **never go down**. Phones on UPS Wi-Fi remain 100% shielded and ad-free. | **None.** Zero PC dependency. |
| **Light returns** | Router reboots, connects to fiber, and instantly pulls DNS from Cloudflare Anycast IPv4. | **None.** All devices auto-reconnect. |
| **Out of home (4G/5G)** | Any mobile device with DoH or Private DNS set to `https://officialum1-hub.onrender.com/dns-query` continues to use the firewall anywhere in the world. | **None.** Worldwide protection. |

---

## 6. Verification Checklist

* [ ] GitHub repo synced: [officialumsmcllc/firwallum1](https://github.com/officialumsmcllc/firwallum1)
* [ ] Render web service deployed and showing "Live"
* [ ] Cloudflare Zero Trust location active with 2 Anycast IPv4s
* [ ] Huawei HG8245C router DHCP Primary/Secondary DNS updated
* [ ] Tested ad-blocking on smartphone connected to Wi-Fi
* [ ] Verified live query logs appearing on Render Dashboard
