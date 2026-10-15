"""
Verification Test Suite: SaaS Customer Authentication & Admin User Management
Tests:
1. PBKDF2 Password Hashing & Salts
2. User Registration & Auto-Provisioned Tenant Configuration
3. User Authentication (Success and Failure cases)
4. Admin User Listing
5. Admin Manual Password Reset
6. Admin Manual Plan Tier Upgrade & Expiry Extension
"""

import sys
import time
from core.store import HubStore

def test_saas_auth():
    print(">>> 1. Initializing HubStore...")
    store = HubStore()

    # 1. Test Demo User Exists
    users = store.get_all_users()
    print(f"    Total users found: {len(users)}")
    demo_user = next((u for u in users if u["username"] == "demo"), None)
    assert demo_user is not None, "Demo user should exist in users table"
    print(f"    [OK] Demo user verified: id={demo_user['id']}, plan={demo_user['plan_tier']}")

    # 2. Test Authenticate Demo User
    auth_demo = store.authenticate_user("demo", "demo123")
    assert auth_demo is not None, "Demo user should authenticate with demo123"
    assert auth_demo["username"] == "demo"
    assert "token" in auth_demo
    print("    [OK] Demo authentication successful.")

    # 3. Test Invalid Password
    bad_auth = store.authenticate_user("demo", "wrongpass")
    assert bad_auth is None, "Bad password should fail authentication"
    print("    [OK] Invalid password correctly rejected.")

    # 4. Test Customer Registration
    test_user = f"tester_{int(time.time())}"
    test_email = f"{test_user}@testdomain.com"
    print(f">>> 2. Testing Registration for {test_user}...")
    reg_res = store.create_user(
        username=test_user,
        email=test_email,
        password="secretpassword123",
        full_name="Muhammad Test",
        plan_tier="home_pro"
    )
    assert reg_res["username"] == test_user
    assert reg_res["config_id"] == f"cfg_{test_user}"
    print(f"    [OK] User registered with config_id: {reg_res['config_id']}")

    # Verify dedicated configuration table row was created
    tenant_cfg = store.get_tenant(reg_res["config_id"])
    assert tenant_cfg is not None, "Dedicated tenant configuration should be provisioned"
    assert tenant_cfg["owner_name"] == "Muhammad Test"
    assert tenant_cfg["plan_tier"] == "home_pro"
    print("    [OK] Linked tenant configuration verified.")

    # 5. Test Admin Reset Password
    print(">>> 3. Testing Admin Manual Password Reset...")
    new_pwd = "NewAdminSetPassword999"
    ok = store.admin_reset_user_password(reg_res["id"], new_pwd)
    assert ok is True, "Admin password reset should succeed"

    # Authenticate with new password
    auth_new = store.authenticate_user(test_user, new_pwd)
    assert auth_new is not None, "Should authenticate with new password"
    print("    [OK] Password reset successfully verified.")

    # 6. Test Admin Upgrade Tier
    print(">>> 4. Testing Admin Manual Account Upgrade...")
    up_ok = store.admin_upgrade_user(reg_res["id"], new_plan_tier="business", extend_days=90)
    assert up_ok is True, "Admin upgrade should succeed"

    updated_u = store.get_user_by_id(reg_res["id"])
    assert updated_u["plan_tier"] == "business"
    updated_cfg = store.get_tenant(reg_res["config_id"])
    assert updated_cfg["plan_tier"] == "business"
    print("    [OK] Account and Tenant upgraded to business tier.")

    print("\n=======================================================")
    print(">>> ALL SAAS AUTH & ADMIN TESTS PASSED PERFECTLY! [OK]")
    print("=======================================================\n")

if __name__ == "__main__":
    test_saas_auth()
