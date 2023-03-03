#!/usr/bin/env python3
#
# Unofficial Buypass SCProxy implementation
#
# Only supports smartcard login, not signing or other use-cases.
#
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import json
import random
from urllib.parse import unquote

import smartcard.System
import smartcard.Session
from smartcard.util import toHexString, toBytes

class ScproxyHandler(BaseHTTPRequestHandler):

    CORS_ORIGIN = 'https://secure.buypass.no'

    sessions = {}
    refs = {}

    def do_GET(self):
        self.send_404()

    def do_POST(self):
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
        self.send_response(200, 'ok')
        self.send_header('Access-Control-Allow-Methods', 'OPTIONS, POST')
        self.send_header("Access-Control-Allow-Headers", 'Content-Type')
        self.end_headers()

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', self.CORS_ORIGIN)
        BaseHTTPRequestHandler.end_headers(self)

    #
    # Helper methods
    #

    def send_404(self):
        self.send_response(404)

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

    #
    # Request handlers (see do_POST)
    #

    def handle_version(self):
        self.send_json({ 'version': '1.4.1.16', 'port': 31505 })

    def handle_list(self):
        # status must be 301 (no card) or 302 (card present) to be recognized by Buypass
        # status must be >= 302 for Buypass pin-change app
        # TODO proper status based on card reader
        readers = [{ 'cardstatus': 302, 'name': r.name } for r in smartcard.System.readers()]
        self.send_json({ 'readers': readers, 'errorcode': 0, 'errordetail': 0 })

    def handle_getref(self):
        ref = random.randrange(0,10**8)
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
            apduBytes = toBytes(apdu['apdu'])

            # special command to handle PIN entry, we decrypt PIN and send a different command
            #   FF FF 01 04        - indicator about special packet
            #   xx xx xx xx        - ref to unscramble pin with
            #   05                 - length of apdu prefix (guess)
            #   04                 - length of pin (guess)
            #   A0 20 00 82 08     - apdu prefix
            #   xx xx xx xx        - scrambled pin
            #   FF FF FF FF        - placeholder (for longer pins)
            #   FF FF FF FF        - padding?
            if apduBytes[0:4] == [0xff, 0xff, 0x01, 0x04]:
                # TODO handle length bytes, to support other APDUs and PIN lengths
                if apduBytes[8] != 5:
                    print('PIN verification only supported with 5-byte APDU prefix')
                    self.send_404()
                    return
                if apduBytes[9] != 4:
                    print('PIN verification only supported with 4-digit PIN')
                    self.send_404()
                    return
                # unscramble pin with ref
                ref = (((apduBytes[4] << 8) + apduBytes[5] << 8) + apduBytes[6] << 8) + apduBytes[7]
                refdata = self.refs[ref] # TODO handle missing ref
                pin = apduBytes[15:19]
                pin = [d ^ refdata[i] ^ refdata[i+len(pin)] for i, d in enumerate(pin)]
                # replace with real apdu
                apduBytes = apduBytes[10:15] + pin + [0xff, 0xff, 0xff, 0xff] + [0xff, 0xff, 0xff, 0xff]

            response, sw1, sw2 = session.sendCommandAPDU(apduBytes)

            # status indicates we need another request to fech data
            if sw1 == 0x61:
                response, sx1, sx2 = session.sendCommandAPDU([0x00, 0xc0, 0x00, 0x00, sw2])
                data = response
            # special case: response of two bytes, add status to bytes
            # not sure why this is needed, but it makes the responses match the official client
            elif response and apduBytes[-1] == 2:
                data = [*response, sw1, sw2]
            # response
            elif response:
                data = response
            # no response, just status
            else:
                data = [sw1, sw2]

            responses.append({ 'apdu': toHexString(data).replace(' ', '') })
        self.send_json({ 'apduresponses': responses, 'errorcode': 0, 'errordetail': 0 })

if __name__ == '__main__':
    httpd = HTTPServer(('localhost', 31505), ScproxyHandler)
    sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sslctx.check_hostname = False
    sslctx.load_cert_chain(certfile='certs/scproxy.chain', keyfile='certs/scproxy.key')
    httpd.socket = sslctx.wrap_socket(httpd.socket, server_side=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass

    # TODO close sessions
    httpd.server_close()

