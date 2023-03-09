# SCProxy for Linux

To use [Buypass](https://www.buypass.no/) smartcard, one needs a local proxy to
connect to the smartcard. This solution is called _SCProxy_ or _Javafri_. The
proxy [is available](https://www.buypass.no/hjelp/hjelp-til-smartkort/javafri/hvordan-installere-javafri)
for Windows and Mac OS, but not for Linux.

This program is a basic attempt to get it working on Linux. It's not very
polished, and there are likely to be many corner-cases that aren't handled.
But it allows one to log into websites with a Buypass smartcard.

## Install

1. Install the dependencies:

   - [Python](https://www.python.org) version 3.10 or later
   - [pyscard](https://pyscard.sourceforge.io/), Python for smart cards
   - [PC/SC-lite](https://pcsclite.apdu.fr/) daemon, for accessing smart cards
   - [OpenSSL](https://www.openssl.org/), for generating certificates

   On Debian-based distributions (incl. Ubuntu), you can install them using:

   ```sh
   apt-get install python3 python3-pyscard pcscd openssl
   ```

2. Clone this repository

   ```sh
   git clone https://github.com/wvengen/scproxy
   cd scproxy
   ```

3. Generate SSL certificates

   ```sh
   sh gencerts.sh
   ```

4. Install root certificate (generated in the previous step)

   For _Firefox_, the steps are:
   - open the _Preferences_ and activate the _View Certificates_ button;
   - in the _Authorities_ tab, select _Import_;
   - choose the file `certs/root.crt` and trust it to identify websites.

5. Add a user-agent switcher to your web browser, you'll need it later.


## Use

1. Start SCProxy.

   Before logging in with Buypass, you need to make sure SCProxy is running.
   At this moment, you'll need to open a terminal and run

   ```sh
   python3 scproxy.py
   ```

2. In the user-agent switcher, select the _Windows_ platform.

3. Make sure you smartcard reader is connected and the Buypass card inserted.

4. Visit the website you want to login with using Buypass smartcard, and do so.

5. At the end, you can switch back to the terminal and press <kbd>Ctrl-C</kbd>
   to terminate SCProxy.

# Links

- [I'm not the only one](https://www.diskusjon.no/topic/1874608-buypass-med-kortleser-i-ubuntu/)
- [Buypass still recommends the Java plugin on Linux](https://www.diskusjon.no/topic/1874608-buypass-med-kortleser-i-ubuntu/)
  (great they did support Linux some years ago)
- [Technical intro of SCProxy](https://buypassdev.atlassian.net/wiki/spaces/Smartkort/pages/16515133/L+sningsbeskrivelse),
  with [Terminalserver notes](https://buypassdev.atlassian.net/wiki/spaces/Smartkort/pages/26214438/L+sningsbeskrivelse+Terminalserver) (Norwegian)
- [Troubleshooting SCProxy](https://buypassdev.atlassian.net/wiki/spaces/Smartkort/pages/87228452/Troubleshooting+Buypass+Javafri)
- [List of sw1 sw2 in smartcards](https://arfan.wordpress.com/2015/08/13/list-of-sw1-sw2-in-smart-card/)
- ISO 7816-4
- Sniffing [USB with Wireshark](https://nickvsnetworking.com/sim-card-sniffing-visibility-with-wireshark/) and [decoding ISO 7816-4](https://ludovicrousseau.blogspot.com/2019/08/iso-7816-4-spy-using-wireshark.html)

# Technical notes

## Login process

The Buypass website makes POST requests to SCProxy, which listens on https://127.0.0.1:31505

1. On page load: `POST /scard/version/` to check if SCProxy is running and its version is supported.
2. If SCProxy is detected: `POST /scard/list/` to obtain a list of smartcard reader names.
3. If a reader is found: various `POST /scard/apdu/(:reader_name)` to interact with smartcard.
4. On success: `POST /sdcard/getref/` to obtain a shared key to obfuscate the PIN with.
5. After PIN entry, several other `POST /scard/apdu/(:reader_name)` requests.
6. On success, redirect to service, now authenticated.

`POST /scard/apdu/(:reader_name)` handles communication with the smartcard. It has a JSON request body
with APDU commands. Here is a `SELECT MF` (master file) command:

```json
{
"timeout": 10,
"apducommands": [{ "apdu":"00A40000023F00" }],
"session": "0123456789abcdef"
}
```

The `session` is a random string to avoid concurrent requests to the smartcard interfering with each
other.

When a suitable card is inserted, this would return an OK response:

```json
{
"apduresponses": [{ "apdu":"9000" }],
"errorcode": 0,
"errordetail": 0
}
```

## Testing

To play around with the API, you can use [curl](https://curl.se) e.g. as follows:

```sh
curl --insecure -H 'Sec-Fetch-Mode: cors' -H 'Origin: https://secure.buypass.no' \
     --data-raw '' https://127.0.0.1:31505/scard/list/
```

# License

This program is licensed under the [GNU GPL v3 or later](LICENSE.md).
