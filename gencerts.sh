#!/bin/sh
mkdir -p certs/newcerts
touch certs/index.txt
export SUBJECT_ALT_NAME=localhost
export SUBJECT_ALT_IP=127.0.0.1

[ -e certs/root.crt ] || openssl req -config openssl.cnf -x509 -nodes -newkey rsa -keyout certs/root.key -out certs/root.crt -subj '/C=NO/O=root'
openssl req -config openssl.cnf -nodes -newkey rsa -keyout certs/scproxy.key -out certs/scproxy.csr -extensions v3_req -subj "/C=NO/CN=${SUBJECT_ALT_NAME}"
openssl ca -config openssl.cnf -batch -rand_serial -out certs/scproxy.crt -notext -extensions v3_req -infiles certs/scproxy.csr

cat certs/scproxy.crt certs/root.crt >certs/scproxy.chain
