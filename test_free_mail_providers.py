#!/usr/bin/env python3
"""Test all 4 free mail providers"""
import sys
import time
import traceback

sys.path.insert(0, ".")

from core.base_mailbox import (
    TempMailLolMailbox,
    MailTmMailbox,
    TempMailWebMailbox,
    AitreMailbox,
)

def test_provider(name, mailbox, needs_email=False):
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    try:
        # get_email
        print(f"[{name}] Calling get_email()...")
        account = mailbox.get_email()
        print(f"[{name}] Got email: {account.email}")
        print(f"[{name}] account_id: {account.account_id}")

        if not account.email:
            raise RuntimeError("Empty email returned")

        # get_current_ids
        print(f"[{name}] Calling get_current_ids()...")
        ids = mailbox.get_current_ids(account)
        print(f"[{name}] Current message IDs: {ids}")

        # wait_for_code (short timeout since no real email will arrive)
        print(f"[{name}] Calling wait_for_code() with 10s timeout (no email expected)...")
        try:
            code = mailbox.wait_for_code(account, keyword="test", timeout=10, before_ids=ids)
            print(f"[{name}] Got code: {code}")
        except TimeoutError:
            print(f"[{name}] Timeout (expected - no email sent)")

        print(f"[{name}] ✓ SUCCESS")
        return True
    except Exception as e:
        print(f"[{name}] ✗ FAILED: {e}")
        traceback.print_exc()
        return False

results = {}

# 1. TempMailLol
results["tempmail_lol"] = test_provider("TempMailLol", TempMailLolMailbox())

# 2. MailTm
results["mailtm"] = test_provider("MailTm", MailTmMailbox())

# 3. TempMailWeb (uses browser, may be slower)
results["tempmail_web"] = test_provider("TempMailWeb", TempMailWebMailbox())

# 4. Aitre (requires a fixed email - we generate one for test)
print(f"\n{'='*60}")
print("Testing: Aitre (with test email)")
print(f"{'='*60}")
try:
    # Aitre requires a fixed email. Let's use a test one.
    aitre = AitreMailbox(email="test@example.com")
    account = aitre.get_email()
    print(f"[Aitre] Got email: {account.email}")
    ids = aitre.get_current_ids(account)
    print(f"[Aitre] Current message IDs: {ids}")
    try:
        code = aitre.wait_for_code(account, keyword="test", timeout=10, before_ids=ids)
        print(f"[Aitre] Got code: {code}")
    except TimeoutError:
        print(f"[Aitre] Timeout (expected - no email sent)")
    print(f"[Aitre] ✓ SUCCESS")
    results["aitre"] = True
except Exception as e:
    print(f"[Aitre] ✗ FAILED: {e}")
    traceback.print_exc()
    results["aitre"] = False

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for name, ok in results.items():
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"  {name}: {status}")

all_ok = all(results.values())
print(f"\nOverall: {'ALL PASS' if all_ok else 'SOME FAILED'}")
