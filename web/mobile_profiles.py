"""
OFFICIALUM1 — Native Device Profile Generator (Zero-App Customer Onboarding)
Generates native configuration profiles for:
- Apple iOS / iPadOS / macOS (.mobileconfig XML plist)
- Android Private DNS (DoT / DoH configuration)
- Windows 11 Native DoH Encrypted DNS
"""

import uuid
import urllib.parse
from typing import Dict, Any

def generate_apple_mobileconfig(config_id: str, device_name: str, host: str = "hub.officialum1.com") -> str:
    """
    Generates an Apple-compliant .mobileconfig XML profile (RFC 8484 DoH).
    iOS, iPadOS, and macOS natively load this profile without needing any App Store app.
    """
    safe_dev = urllib.parse.quote(device_name.strip().replace(" ", "-"))
    clean_name = device_name.strip().replace("-", " ").title()
    doh_url = f"https://{host}/dns-query/{config_id}/{safe_dev}"
    
    payload_uuid1 = str(uuid.uuid4()).upper()
    payload_uuid2 = str(uuid.uuid4()).upper()

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>PayloadContent</key>
    <array>
        <dict>
            <key>DNSSettings</key>
            <dict>
                <key>DNSProtocol</key>
                <string>HTTPS</string>
                <key>ServerURL</key>
                <string>{doh_url}</string>
            </dict>
            <key>PayloadDescription</key>
            <string>Configures encrypted DNS-over-HTTPS (DoH) for OFFICIALUM1 Cloud Security Shield.</string>
            <key>PayloadDisplayName</key>
            <string>OFFICIALUM1 - {clean_name}</string>
            <key>PayloadIdentifier</key>
            <string>com.officialum1.dns.{config_id}.{safe_dev}</string>
            <key>PayloadType</key>
            <string>com.apple.dnsSettings.managed</string>
            <key>PayloadUUID</key>
            <string>{payload_uuid1}</string>
            <key>PayloadVersion</key>
            <integer>1</integer>
        </dict>
    </array>
    <key>PayloadDescription</key>
    <string>OFFICIALUM1 Cloud Security &amp; Parental Shield Profile for {clean_name}</string>
    <key>PayloadDisplayName</key>
    <string>OFFICIALUM1 ({clean_name})</string>
    <key>PayloadIdentifier</key>
    <string>com.officialum1.profile.{config_id}.{safe_dev}</string>
    <key>PayloadOrganization</key>
    <string>OfficialUM1 Security Hub</string>
    <key>PayloadRemovalDisallowed</key>
    <false/>
    <key>PayloadType</key>
    <string>Configuration</string>
    <key>PayloadUUID</key>
    <string>{payload_uuid2}</string>
    <key>PayloadVersion</key>
    <integer>1</integer>
</dict>
</plist>
"""
    return xml_content

def get_device_pairing_info(config_id: str, device_name: str, host: str = "hub.officialum1.com") -> Dict[str, Any]:
    """
    Returns platform-specific instructions and direct URLs for zero-install customer pairing.
    """
    safe_dev = urllib.parse.quote(device_name.strip().replace(" ", "-"))
    clean_name = device_name.strip().replace("-", " ").title()
    doh_url = f"https://{host}/dns-query/{config_id}/{safe_dev}"
    apple_profile_url = f"https://{host}/api/devices/apple-profile?config={config_id}&name={safe_dev}"
    android_dot_hostname = f"l7zasdrw78.cloudflare-gateway.com"

    return {
        "device_name": clean_name,
        "device_tag": safe_dev,
        "config_id": config_id,
        "doh_url": doh_url,
        "apple_profile_url": apple_profile_url,
        "android_dot_hostname": android_dot_hostname,
        "windows_setup_script": f'Set-DnsClientServerAddress -InterfaceAlias "Wi-Fi" -ServerAddresses ("142.93.19.40")',
        "instructions": {
            "apple_ios": f"Open Safari on your iPhone/iPad, visit {apple_profile_url}, tap 'Allow', then open Settings -> Profile Downloaded -> Install.",
            "android": f"Open Settings -> Network & internet -> Private DNS -> enter: {doh_url}",
            "browser": f"Open Chrome/Edge/Firefox -> Settings -> Security -> Use Secure DNS -> Custom -> enter: {doh_url}"
        }
    }
