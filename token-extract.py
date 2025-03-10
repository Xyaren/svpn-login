#!/usr/bin/env python3
import os
import subprocess
import sys
from argparse import ArgumentParser
from getpass import getpass
from threading import Thread
from typing import Optional

import mechanize
from mechanize import CookieJar
from pyotp import TOTP

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.0.0 Safari/537.36'


def log(string):
    print(string, file=sys.stderr)


def read_page(resp):
    # log("URL: " + resp.geturl())
    return resp.read().decode("utf-8")


def extract_cookie(b):
    cookiejar: CookieJar = b.cookiejar
    cookie = list(filter(None, [c if c.name == 'MRHSession' else None for c in cookiejar]))[0].value
    return cookie


def prompt(prompt=None):
    if prompt:
        sys.stderr.write(str(prompt))
    return input()


def parse_args():
    parser = ArgumentParser()
    parser.add_argument("-s", "--server", dest="server", help="Server to connect to", required=True)
    parser.add_argument("-u", "--username", dest="username", help="Username", required=False)
    parser.add_argument("-p", "--password", dest="password", help="Password", required=False)
    parser.add_argument("-t", "--otp-token", dest="totp", help="OTP Token", required=False)
    parser.add_argument("-o", "--open-mode", dest="open_mode", help="Open Mode", default="direct",
                        choices=["xdg", "direct"], required=False)
    return parser.parse_args()


args = parse_args()
username = args.username
password = args.password
server = args.server
totp: Optional[TOTP] = None

if args.totp is not None:
    totp = TOTP(args.totp)
    # check early for errors
    totp.now()

#log("Extracting Token via %s" % server)

browser = mechanize.Browser()
browser.addheaders = [('User-Agent', USER_AGENT)]

log("🌐 Opening %s ..." % server)
login_page = browser.open("https://%s/" % server)
currentPageBody = read_page(login_page)

session_token = None
while session_token is None:
    if "logon_page" in currentPageBody \
            and "auth_form" in currentPageBody \
            and "<input type='text' name='username'" in currentPageBody \
            and "<input type='password' name='password'" in currentPageBody:
        log("🌐 Page: Login")

        browser.select_form(id="auth_form")
        # MUST be lowercase without @...
        browser["username"] = username or prompt("Username (without suffix): ").lower().strip()
        browser["password"] = password or getpass("Password: ", stream=sys.stderr)

        log("🪪  Logging in using username & password")
        currentPageBody = read_page(browser.submit())
    elif "no_inspection_host_form" in currentPageBody and "no-inspection-host" in currentPageBody:
        log("🌐 Page: Endpoint Inspection Prompt.")

        url = "f5-epi://" + server + "?server=" + server + "&protocol=https&port=443&sid=" + extract_cookie(browser)

        if args.open_mode == "xdg":
            cmd = 'bash -x /usr/bin/xdg-open \'{0}\''.format(url)
        elif args.open_mode == "direct":
            cmd = '/opt/f5/epi/f5epi \'{0}\''.format(url)
        else:
            raise Exception("Unknown Open Mode")

        log("🔍 Starting Endpoint Inspector (EPI)...")
        log("🔍 Opening: " + cmd)
        process = subprocess.Popen(cmd, env=os.environ.copy(), shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)


        def logstream(stream, loggercb):
            while True:
                out = stream.readline()
                if out:
                    loggercb(out.rstrip().decode("utf-8"))
                else:
                    break


        stdout_thread = Thread(target=logstream, args=(process.stdout, lambda s: log("🔍 [EPI]: {}".format(s))))
        stderr_thread = Thread(target=logstream, args=(process.stderr, lambda s: log("🔍 [EPI]: {}".format(s))))
        stdout_thread.start()
        stderr_thread.start()

        log("🔍 Waiting for endpoint inspector to finish...")
        process.wait()
        stdout_thread.join()
        stderr_thread.join()

        status_res = browser.open_novisit("https://%s/my.status.eps" % server)
        read_page(status_res)
        resp = browser.open("https://%s/my.policy" % server)
        currentPageBody = read_page(resp)
    elif "auth_form" in currentPageBody and "One Time Token" in currentPageBody:
        log("🌐 Page: OTP")

        log("🔑 Entering One Time Token...")
        browser.select_form(id="auth_form")
        browser["otp"] = totp.now() if totp is not None else prompt("🔑 OTP Token: ")
        currentPageBody = read_page(browser.submit())
    elif "auth_form" in currentPageBody and "Enter Your Microsoft verification code" in currentPageBody:
        log("🌐 Page: Microsoft Verification")

        log("#️⃣  Entering Microsoft Verification...")
        browser.select_form(id="auth_form")
        browser["_F5_challenge"] = totp.now() if totp is not None else prompt("#️⃣ Microsoft Verification Code: ")
        currentPageBody = read_page(browser.submit())
    else:
        sessionId = extract_cookie(browser)
        break

# Print to console for piping
print(sessionId)
