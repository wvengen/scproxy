#!/usr/bin/env python3
from http.server import HTTPServer, BaseHTTPRequestHandler
import ssl
import json
from urllib.parse import unquote

import smartcard.System
import smartcard.Session
from smartcard.util import toHexString, toBytes

class ScproxyHandler(BaseHTTPRequestHandler):

    CORS_ORIGIN = 'https://secure.buypass.no'

    connections = {}
    sessions = {}

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

    def get_connection(self, name):
        conn = self.connections.get(name)
        if not conn:
            matching_readers = [r for r in smartcard.System.readers() if r.name == name]
            conn = matching_readers[0].createConnection() # TODO handle disappeared reader
            self.connections[name] = conn
            conn.connect()
        return conn

    def get_session(self, name, sid):
        session = self.sessions.get(sid)
        if not session:
            session = smartcard.Session(self.get_connection(name))
            self.sessions[sid] = session
        return session

    def close_sessions(self):
        for name, s in self.sessions:
            s.close()
        self.sessions = {}

    def close_connections(self):
        for name, c in self.connections:
            c.disconnect()
        self.connections = {}

    #
    # Request handlers (see do_POST)
    #

    def handle_version(self):
        self.send_json({ 'version': '1.4.1.16', 'port': 31505 })
        #self.send_json({ 'version': '1.0', 'port': 31505 })

    def handle_list(self):
        # status must be 301 or 302 to be recognized by Buypass
        # TODO proper status
        readers = [{ 'cardstatus': 301, 'name': r.name } for r in smartcard.System.readers()]
        self.send_json({ 'readers': readers, 'errorcode': 0 })

    def handle_getref(self):
        self.send_404() # no idea what this is for, yet
        # self.send_json({ 'ref': None, 'data': None })

    def handle_disconnect(self):
        # only called when client version <= 1.3
        self.close_sessions()
        self.close_connections()
        self.send_response(200)
        self.send_headers()

    def handle_apdu(self, reader):
        body = self.get_json_body()
        session = self.get_session(reader, body['session'])
        responses = []
        for apdu in body['apducommands']:
            print('tx', apdu)
            response, sw1, sw2 = session.sendCommandAPDU(toBytes(apdu['apdu']))
            print('rx', response, sw1, sw2)
            responses.append({ 'apdu': toHexString(sw1) + toHexString(sw2) })
        self.send_json({ 'apduresponses': responses })

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
    
    # TODO close sessions and disconnect readers
    httpd.server_close()

