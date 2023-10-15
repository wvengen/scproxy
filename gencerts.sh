#!/bin/sh

if [ "$1" = "-h" -o "$1" = "--help" ]; then
  echo "Usage: $0" 1>&2
  echo "       $0 -k|--keep" 1>&2
  echo "       $0 -h|--help" 1>&2
  exit 0
fi

mkdir -p certs/newcerts
touch certs/index.txt
export SUBJECT_ALT_NAME=localhost
export SUBJECT_ALT_IP=127.0.0.1

[ -e certs/root.crt -a -e certs/root.key ] || openssl req -config openssl.cnf -x509 -nodes -newkey rsa -keyout certs/root.key -out certs/root.crt -subj '/C=NO/O=root'
openssl req -config openssl.cnf -days 3650 -nodes -newkey rsa -keyout certs/scproxy.key -out certs/scproxy.csr -extensions v3_req -subj "/C=NO/CN=${SUBJECT_ALT_NAME}"
openssl ca -config openssl.cnf -batch -rand_serial -out certs/scproxy.crt -notext -extensions v3_req -infiles certs/scproxy.csr

cat certs/scproxy.crt certs/root.crt >certs/scproxy.chain

# be safe and remove the root key (as it will be installed in the web browser)
if [ "$1" != "-k" -a "$1" != "--keep" ]; then
	rm -f certs/root.key
fi
