#!/usr/bin/env python3
#
# Unofficial Buypass SCProxy implementation
#
# Only supports smartcard login, not signing or other use-cases.
#
from http.server import HTTPServer, BaseHTTPRequestHandler
import os
import ssl
import json
import random
import socket
import time
from urllib.parse import unquote

import smartcard.System
import smartcard.Session
from smartcard.util import toHexString, toBytes

class ScproxyHandler(BaseHTTPRequestHandler):

    PORT = 31505
    VERSION = '1.5.2'
    CORS_ORIGIN = 'https://secure.buypass.no'

    sessions = {}
    refs = {}

    server_version = 'SCProxy/' + VERSION

    def do_GET(self):
        if not self.security_check(): return

        self.send_404()

    def do_POST(self):
        if not self.security_check(): return

        if self.path == '/scard/version/':
            self.handle_version()
        elif self.path == '/scard/list/':
            self.handle_list()
        elif self.path == '/scard/getref/':
            self.handle_getref()
        elif self.path.startswith('/scard/apdu/'):
            self.handle_apdu(unquote(self.path[12:]))
        elif self.path == '/scard/disconnect/':
            self.handle_disconnect()
        else:
            self.send_404()

    def do_OPTIONS(self):
        if not self.security_check(): return

        self.send_response(200, 'ok')
        self.send_header('Access-Control-Allow-Methods', 'POST')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', self.CORS_ORIGIN)
        BaseHTTPRequestHandler.end_headers(self)

    #
    # Helper methods
    #

    def security_check(self):
        # security checks to avoid e.g. forms accessing this
        if self.headers['Sec-Fetch-Mode'] != 'cors':
            self.send_403()
            return False
        if self.headers['Origin'] != self.CORS_ORIGIN:
            self.send_403()
            return False
        else:
            return True

    def send_404(self):
        self.send_response(404)
        self.end_headers()

    def send_403(self):
        self.send_response(403)
        self.end_headers()

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def get_json_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        return json.loads(self.rfile.read(content_length))

    def get_session(self, name, sid):
        session = self.sessions.get(sid)
        if not session:
            session = smartcard.Session(name)
            self.sessions[sid] = session
        return session

    def close_sessions(self):
        for s in self.sessions.values():
            s.close()
        self.sessions = {}

    def unscramble_apdu(self, bytesIn):
        # Example incoming APDU:
        #   FF FF 01 04        - indicator about special packet
        #   xx xx xx xx        - ref to unscramble pin with
        #   05                 - length of apdu prefix (guess)
        #   04                 - length of pin (guess)
        #   A0 20 00 82 08     - apdu prefix
        #   xx xx xx xx        - scrambled pin
        #   FF FF FF FF        - placeholder (for longer pins)
        #   FF FF FF FF        - padding?
        bytesOut = []
        # lookup ref for data to unscramble
        ref = (((bytesIn[4] << 8) + bytesIn[5] << 8) + bytesIn[6] << 8) + bytesIn[7]
        refdata = self.refs[ref] # TODO handle missing ref
        # data lengths
        prefixLen = bytesIn[8]
        pinLen = bytesIn[9]
        # prefix
        bytesOut += bytesIn[10:(10+prefixLen)]
        # unscramble pin
        pin = bytesIn[(10+prefixLen):(10+prefixLen+pinLen)]
        pin = [d ^ refdata[i] ^ refdata[i+len(pin)] for i, d in enumerate(pin)]
        bytesOut += pin
        # suffix
        bytesOut += bytesIn[(10+prefixLen+pinLen):]
        return bytesOut

    #
    # Request handlers (see do_POST)
    #

    def handle_version(self):
        self.send_json({ 'version': self.VERSION, 'port': self.PORT })

    def handle_list(self):
        # status must be 301 (no card) or 302 (card present) to be recognized by Buypass
        # status must be >= 302 for Buypass pin-change app
        # TODO proper status based on card reader
        readers = [{ 'cardstatus': 302, 'name': r.name } for r in smartcard.System.readers()]
        self.send_json({ 'readers': readers, 'errorcode': 0, 'errordetail': 0 })

    def handle_getref(self):
        ref = random.randrange(0,0x80000000) # 4 bytes, except highest bit to avoid signed/unsigned issues
        data = [random.randrange(0x100) for r in range(16)]
        # TODO drop old entries
        self.refs[ref] = data
        self.send_json({ 'ref': ref, 'data': toHexString(data).replace(' ', '') })

    def handle_disconnect(self):
        # only called when client version >= 1.3
        body = self.get_json_body()
        sid = body['session']
        s = self.sessions.get(sid)
        if s:
            s.close()
            self.sessions.pop(sid)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_404()

    def handle_apdu(self, reader):
        body = self.get_json_body()
        session = self.get_session(reader, body['session'])
        responses = []
        for apdu in body['apducommands']:
            data = self.handle_apdu_command(session, toBytes(apdu['apdu']))
            responses.append({ 'apdu': toHexString(data).replace(' ', '') })
        self.send_json({ 'apduresponses': responses, 'errorcode': 0, 'errordetail': 0 })

    def handle_apdu_command(self, session, apduBytes):

        # special command to handle PIN entry, we decrypt PIN and send a different command
        if apduBytes[0:4] == [0xff, 0xff, 0x01, 0x04]:
            apduBytes = self.unscramble_apdu(apduBytes)

        response, sw1, sw2 = session.sendCommandAPDU(apduBytes)

        # status indicates we need another request to fetch data
        if sw1 == 0x61:
            response, sx1, sx2 = session.sendCommandAPDU([0x00, 0xc0, 0x00, 0x00, sw2])
            data = response
        # special case: response of two bytes, add status to bytes
        # not sure why this is needed, but it makes the responses match the official proxy
        elif response and apduBytes[-1] == 2:
            data = [*response, sw1, sw2]
        # response
        elif response:
            data = response
        # no response, just status
        else:
            data = [sw1, sw2]

        # in case of 'class not supported', fake success (may help in some cases)
        # don't enable this by default, it may sollicitate strange behaviour
        #if data == [0x6e, 0x00]: data = [0x90, 0x00]

        return data


if __name__ == '__main__':

    def get_systemd_socket():
        """Get socket from systemd with socket activation"""
        SYSTEMD_FIRST_SOCKET_FD = 3
        return socket.fromfd(SYSTEMD_FIRST_SOCKET_FD, HTTPServer.address_family, HTTPServer.socket_type)

    def setup_ssl(httpd, datadir):
        """Setup SSL for HTTP server"""
        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.check_hostname = False
        sslctx.load_cert_chain(certfile=datadir+'/certs/scproxy.chain', keyfile=datadir+'/certs/scproxy.key')
        httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)

    # figure out where the certificates are located
    datadir = None
    for prefix in ['/var/lib/scproxy', '.']:
        if os.path.isfile(prefix + '/certs/scproxy.crt'):
            datadir = prefix
            break
    if not datadir:
        raise Exception('Could not find certificate, did you generate it?')

    if os.environ.get('LISTEN_PID', None) == str(os.getpid()):
        # systemd socket activation
        httpd = HTTPServer(('localhost', ScproxyHandler.PORT), ScproxyHandler, bind_and_activate=False)
        httpd.timeout = 1
        httpd.socket = get_systemd_socket()
        httpd.server_activate()
        setup_ssl(httpd, datadir)

        SHUTDOWN_DELAY = 60
        start = time.monotonic()
        while time.monotonic() < start + SHUTDOWN_DELAY:
            httpd.handle_request()

        # connections are closed by smartcard's finalizers
        httpd.server_close()

    else:
        # regular http server
        httpd = HTTPServer(('localhost', ScproxyHandler.PORT), ScproxyHandler)
        setup_ssl(httpd, datadir)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass

        # connections are closed by smartcard's finalizers
        httpd.server_close()

