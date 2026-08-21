#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#   "requests==2.32.4",
#   "beautifulsoup4==4.13.5",
# ]
# ///
"""Azure AD (AAD) + ADFS SAML authentication. Returns a SAML assertion string.

Usage:
    from aad_saml_auth import authenticate

    assertion = authenticate(
        username="some_account@example.com",
        password="",
        app_id="00000000-0000-0000-0000-000000000000",  # Azure AD Enterprise Application (SAML SSO) ID
        env="dev",                                      # looked up via load_totp(env)
    )
    # mfa_mode: "auto" (default, auto OTP else approve), "otp" (auto OTP, no approve
    #           fallback — fails if unavailable), "approve" (Entra approve notification)
    # assertion is a base64-encoded SAML XML string, pass it to your service's SDK:
    # e.g. AWS:  boto3_sts.assume_role_with_saml(SAMLAssertion=assertion, ...)
    # e.g. other: decode with base64.b64decode(assertion) to inspect the XML

"""

import json
import os
import re
import time
import hmac
import hashlib
import struct
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

AAD_BASE = "https://account.activedirectory.windowsazure.com"
DEBUG    = False


def load_totp(env: str) -> str:
    """Read a TOTP secret for `env` from the shared totp.ini file."""
    props = Path(os.path.expandvars(r"totp.ini"))
    if not props.exists():
        print(f"[totp] ini file not found: {props}")
        return ""
    for line in props.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith(f"{env}="):
            payload = line.split("=", 1)[1].strip()
            parts = [p.strip() for p in payload.split(",") if p.strip()]
            if not parts:
                print(f"[totp] no secret found for env '{env}' in {props}")
            return parts[0] if parts else ""
    print(f"[totp] no entry for env '{env}' in {props}")
    return ""


def _base32_decode(secret: str) -> bytes:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    clean = re.sub(r"\s+", "", secret or "").rstrip("=").upper()
    bits = ""
    for ch in clean:
        idx = alphabet.find(ch)
        if idx < 0:
            raise RuntimeError(f"Invalid base32 character in TOTP secret: {ch}")
        bits += format(idx, "05b")
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        out.append(int(bits[i:i + 8], 2))
    return bytes(out)


def _totp_now(secret: str, period: int = 30, digits: int = 6) -> str:
    key = _base32_decode(secret)
    counter = int(time.time() // period)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def _config(html: str) -> dict:
    idx = html.find("$Config=")
    if idx == -1:
        return {}
    obj, _ = json.JSONDecoder().raw_decode(html, idx + len("$Config="))
    return obj


def _form(html: str, base_url: str) -> tuple[str, dict]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form")
    if not form:
        return "", {}
    action = form.get("action", "")
    if action and not action.startswith("http"):
        action = urljoin(base_url, action)
    return action, {i["name"]: i.get("value", "") for i in form.find_all("input") if i.get("name")}


def _saml(html: str) -> str:
    tag = BeautifulSoup(html, "html.parser").find("input", {"name": "SAMLResponse"})
    return tag["value"] if tag else ""


def _get_credential_type(session: requests.Session, cfg: dict, username: str) -> dict:
    r = session.post(
        cfg["urlGetCredentialType"],
        json={
            "username": username, "isOtherIdpSupported": True, "checkPhones": False,
            "isRemoteNGCSupported": False, "isCookieBannerShown": False, "isFidoSupported": False,
            "originalRequest": cfg.get("sCtx", ""), "flowToken": cfg.get("sFT", ""),
        },
        headers={
            "canary": cfg.get("apiCanary", ""), "client-request-id": cfg.get("correlationId", ""),
            "hpgact": str(cfg.get("hpgact", "")), "hpgid": str(cfg.get("hpgid", "")),
            "hpgrequestid": cfg.get("sessionId", ""),
        },
    )
    r.raise_for_status()
    return r.json()


def _adfs_login(session: requests.Session, fed_url: str, username: str, password: str) -> requests.Response:
    r = session.get(fed_url)
    r.raise_for_status()
    action, fields = _form(r.text, r.url)
    if not action:
        raise RuntimeError("ADFS login form not found")
    fields.update({"UserName": username, "Password": password, "AuthMethod": "FormsAuthentication"})
    return session.post(action + "&RedirectToIdentityProvider=AD+Authority", data=fields)


def _mfa_otp(session: requests.Session, cfg: dict, otp: str) -> requests.Response:
    available = [p["authMethodId"] for p in cfg.get("arrUserProofs", [])]
    if "PhoneAppOTP" not in available:
        raise RuntimeError(f"PhoneAppOTP not available. Available: {available}")

    r = session.post(cfg["urlBeginAuth"], json={"AuthMethodId": "PhoneAppOTP", "Method": "BeginAuth",
                                                 "Ctx": cfg["sCtx"], "FlowToken": cfg["sFT"]})
    r.raise_for_status()
    b = r.json()
    if not b.get("Success"):
        raise RuntimeError(f"BeginAuth failed: {b.get('Message')}")

    r = session.post(cfg["urlEndAuth"], json={"AuthMethodId": "PhoneAppOTP", "Method": "EndAuth",
                                               "Ctx": b["Ctx"], "FlowToken": b["FlowToken"],
                                               "SessionId": b.get("SessionId", ""), "AdditionalAuthData": otp})
    r.raise_for_status()
    e = r.json()
    if e.get("ErrCode", 0) != 0 or not e.get("Success"):
        raise RuntimeError(f"EndAuth failed ({e.get('ErrCode')}): {e.get('Message')}")

    return session.post(cfg["urlPost"], data={cfg["sFTName"]: e["FlowToken"], "request": e["Ctx"],
                                              "login": cfg.get("sPOST_Username", ""), "mfaAuthMethod": "PhoneAppOTP"})


def _mfa_approve(
    session: requests.Session,
    cfg: dict,
    poll_interval_seconds: int = 2,
    timeout_seconds: int = 90,
) -> requests.Response:
    available = [p["authMethodId"] for p in cfg.get("arrUserProofs", [])]
    if "PhoneAppNotification" not in available:
        raise RuntimeError(f"PhoneAppNotification not available. Available: {available}")

    r = session.post(
        cfg["urlBeginAuth"],
        json={
            "AuthMethodId": "PhoneAppNotification",
            "Method": "BeginAuth",
            "Ctx": cfg["sCtx"],
            "FlowToken": cfg["sFT"],
        },
    )
    r.raise_for_status()
    b = r.json()
    if not b.get("Success"):
        raise RuntimeError(f"BeginAuth failed: {b.get('Message')}")

    entropy = b.get("Entropy", 0)
    if entropy:
        print(f"Entra approval required. Number is: {entropy}")
    else:
        print("Entra approval required.")

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        r = session.post(
            cfg["urlEndAuth"],
            json={
                "AuthMethodId": "PhoneAppNotification",
                "Method": "EndAuth",
                "Ctx": b["Ctx"],
                "FlowToken": b["FlowToken"],
                "SessionId": b.get("SessionId", ""),
                "AdditionalAuthData": "",
            },
        )
        r.raise_for_status()
        e = r.json()

        if e.get("ErrCode", 0) != 0:
            raise RuntimeError(f"Approve failed ({e.get('ErrCode')}): {e.get('Message')}")

        if e.get("Success"):
            return session.post(
                cfg["urlPost"],
                data={
                    cfg["sFTName"]: e["FlowToken"],
                    "request": e["Ctx"],
                    "login": cfg.get("sPOST_Username", ""),
                    "mfaAuthMethod": "PhoneAppNotification",
                },
            )

        time.sleep(poll_interval_seconds)

    raise RuntimeError("Timed out waiting for Entra approve notification")


def authenticate(username: str, password: str, app_id: str, env: str, mfa_mode: str = "auto") -> str:
    """Authenticate via AAD + ADFS and return a base64-encoded SAML assertion."""
    session = requests.Session()
    # Non-browser UA required: browser UA triggers ADFS WIA redirect → 401
    session.headers["User-Agent"] = "saml2aws/1.0 (windows amd64) Versent"

    resp = session.get(f"{AAD_BASE}/applications/redirecttofederatedapplication.aspx"
                       f"?Operation=LinkedSignIn&applicationId={app_id}")

    for step in range(10):
        html = resp.text

        if DEBUG:
            c = _config(html)
            print(f"[debug] step={step} pgid={c.get('pgid','?')} status={resp.status_code} url={resp.url}")
            print(f"[debug] snippet: {html[:400]}\n")

        if "ConvergedSignIn" in html:
            cfg     = _config(html)
            fed_url = _get_credential_type(session, cfg, username).get("Credentials", {}).get("FederationRedirectUrl", "")
            if not fed_url:
                raise RuntimeError("ADFS federation URL not found")
            resp = _adfs_login(session, fed_url, username, password)

        elif "ConvergedTFA" in html:
            cfg  = _config(html)
            available = [p["authMethodId"] for p in cfg.get("arrUserProofs", [])]
            print(f"Available MFA methods: {available}")

            if mfa_mode == "otp":
                totp = load_totp(env)
                code = _totp_now(totp) if totp else input("Enter OTP: ").strip()
                # print(f"OTP: {code}")
                resp = _mfa_otp(session, cfg, code)
            elif mfa_mode == "approve":
                print("Waiting for Entra approve notification ...")
                resp = _mfa_approve(session, cfg)
            elif mfa_mode == "auto":
                # Prefer full-auto OTP when a secret is configured and method is available.
                totp = load_totp(env)
                if totp and "PhoneAppOTP" in available:
                    code = _totp_now(totp)
                    # print(f"OTP: {code}")
                    try:
                        resp = _mfa_otp(session, cfg, code)
                    except RuntimeError as ex:
                        if "PhoneAppNotification" in available:
                            print(f"OTP failed, falling back to Entra approve: {ex}")
                            print("Waiting for Entra approve notification ...")
                            resp = _mfa_approve(session, cfg)
                        else:
                            raise
                elif "PhoneAppNotification" in available:
                    print("Waiting for Entra approve notification ...")
                    resp = _mfa_approve(session, cfg)
                else:
                    raise RuntimeError(f"No supported auto MFA method. Available: {available}")
            else:
                raise RuntimeError(f"Unsupported mfa_mode: {mfa_mode}. Use 'auto', 'otp' or 'approve'.")

        elif "KmsiInterrupt" in html:
            cfg  = _config(html)
            resp = session.post(cfg["urlPost"],
                                data={cfg["sFTName"]: cfg["sFT"], "ctx": cfg["sCtx"], "LoginOptions": "1"},
                                allow_redirects=False)
            if resp.status_code in (301, 302):
                resp = session.get(resp.headers["Location"])

        elif "SAMLRequest" in html:
            m = re.search(r"window\.location\s*=\s*['\"]([^'\"]+SAMLRequest[^'\"]+)['\"]", html)
            if not m:
                raise RuntimeError("SAMLRequest URL not found")
            resp = session.get(m.group(1))

        elif assertion := _saml(html):
            return assertion

        elif html.lstrip().startswith("<html><head><title>Working...") and 'name="hiddenform"' in html:
            action, fields = _form(html, resp.url)
            resp = session.post(action, data=fields)

        elif "ConvergedError" in html:
            cfg = _config(html)
            msg = (cfg.get("strMainMessage") or cfg.get("strServiceExceptionMessage")
                   or cfg.get("sErrTxt") or cfg.get("strAdditionalMessage") or "")
            raise RuntimeError(
                f"AAD returned an error page (pgid={cfg.get('pgid')}) at step={step}, url={resp.url}: {msg or 'no message field found'}\n"
                f"Raw config: {json.dumps(cfg, ensure_ascii=False)[:1000]}"
            )

        elif "$Config" in html:
            action, fields = _form(html, resp.url)
            if not action:
                raise RuntimeError(f"Unknown $Config page: {_config(html).get('pgid')}")
            resp = session.post(action, data=fields)

        else:
            raise RuntimeError(f"Unknown page.\nURL: {resp.url}\n{html[:500]}\nRe-run with DEBUG=True.")

    raise RuntimeError("Too many redirects")
