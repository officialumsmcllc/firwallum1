import requests
import time

BASE_URL = "http://127.0.0.1:8088"

def test_full_saas_lifecycle():
    print("=" * 60)
    print(">>> RUNNING FULL SAAS CUSTOMER & ADMIN E2E TEST SUITE")
    print("=" * 60)

    # 1. Test Static Routes
    for route in ["/login", "/", "/admin", "/expired"]:
        res = requests.get(f"{BASE_URL}{route}")
        assert res.status_code == 200, f"Route {route} failed with {res.status_code}"
        print(f"[OK] Route {route} -> HTTP 200 OK")

    # 2. Test Enterprise Login
    print("\n>>> Testing Enterprise Customer Login...")
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "officialum1", "password": "admintelecom"})
    assert res.status_code == 200, f"officialum1 login failed: {res.text}"
    ent_data = res.json()["user"]
    assert ent_data["username"] == "officialum1"
    assert "token" in ent_data
    print(f"[OK] Customer Login Successful: {ent_data['username']} (Tier: {ent_data['plan_tier']})")

    # 3. Test Invalid Login
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "officialum1", "password": "wrongpassword"})
    assert res.status_code == 401, "Bad password should return 401"
    print("[OK] Invalid credentials correctly rejected (401)")

    # 4. Test Customer Registration & Auto-Provisioning
    new_user = f"sub_{int(time.time())}"
    print(f"\n>>> Testing Registration for '{new_user}'...")
    res = requests.post(f"{BASE_URL}/api/auth/register", json={
        "full_name": "Tariq Mahmood",
        "username": new_user,
        "email": f"{new_user}@sub.com",
        "password": "pass1234Secure",
        "plan_tier": "home_pro"
    })
    assert res.status_code == 201, f"Registration failed: {res.text}"
    reg_user = res.json()["user"]
    user_id = reg_user["id"]
    cfg_id = reg_user["config_id"]
    print(f"[OK] User Registered: id={user_id}, config_id={cfg_id}")

    # 5. Verify User in Admin Fleet Table
    print("\n>>> Testing Admin Users Fleet Endpoint...")
    res = requests.get(f"{BASE_URL}/api/admin/users")
    assert res.status_code == 200
    users_list = res.json()["users"]
    target_u = next((u for u in users_list if u["id"] == user_id), None)
    assert target_u is not None, "Registered user should appear in admin users list"
    print(f"[OK] User present in Admin Fleet: {target_u['full_name']} ({target_u['email']})")

    # 6. Test Admin Manual Password Reset
    print("\n>>> Testing Admin Password Reset...")
    new_pass = "ResetByAdmin987!"
    res = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/reset-password", json={"new_password": new_pass})
    assert res.status_code == 200, f"Password reset failed: {res.text}"
    print("[OK] Admin Reset Password endpoint succeeded")

    # Verify Login with new password
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": new_user, "password": new_pass})
    assert res.status_code == 200, "Should authenticate with new password"
    print("[OK] New password authentication verified")

    # 7. Test Admin Upgrade Account Plan & Extension
    print("\n>>> Testing Admin Plan Upgrade...")
    res = requests.post(f"{BASE_URL}/api/admin/users/{user_id}/upgrade", json={"plan_tier": "business", "extend_days": 90})
    assert res.status_code == 200, f"Upgrade failed: {res.text}"
    print("[OK] Account upgraded to business tier (+90 days)")

    # 8. Test Wi-Fi Devices API
    print("\n>>> Testing Wi-Fi Devices & Metering...")
    res = requests.get(f"{BASE_URL}/api/wifi-devices?config=default")
    assert res.status_code == 200
    devices = res.json()
    assert len(devices) > 0
    print(f"[OK] Wi-Fi Devices active: {len(devices)} devices found with live bandwidth")

    print("\n" + "=" * 60)
    print(">>> ALL E2E SAAS TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    test_full_saas_lifecycle()
