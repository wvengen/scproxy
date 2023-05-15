
RUNUSER ?= scproxy
DESTDIR ?=
PREFIX ?= /usr
BINDIR ?= $(PREFIX)/sbin
DATADIR ?= /var/lib/scproxy
SYSCONFDIR ?= /etc
SYSTEMDUNITDIR ?= $(SYSCONFDIR)/systemd/system

.PHONY: all build install uninstall install-bin uninstall-bin install-user uninstall-user install-cert uninstall-cert install-service uninstall-service clean

all: build

build: system/scproxy.service certs/scproxy.key

install: install-bin install-user install-cert install-service

uninstall: uninstall-service uninstall-cert uninstall-user uninstall-bin

install-bin: scproxy.py
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 $< $(DESTDIR)$(BINDIR)

uninstall-bin:
	rm -f $(DESTDIR)$(BINDIR)/scproxy.py

install-user:
	install -d $(DESTDIR)$(DATADIR)
	useradd -d $(DESTDIR)$(DATADIR) --no-user-group --system $(RUNUSER)

uninstall-user:
	userdel $(RUNUSER)
	echo "You may manually remove $(DESTDIR)$(DATADIR)" 1>&2

install-cert: certs/scproxy.chain
	install -d $(DESTDIR)$(DATADIR)/certs
	install -m 0644 -o $(RUNUSER) certs/root.crt $(DESTDIR)$(DATADIR)/certs
	install -m 0600 -o $(RUNUSER) certs/scproxy.key $(DESTDIR)$(DATADIR)/certs
	install -m 0644 -o $(RUNUSER) certs/scproxy.chain $(DESTDIR)$(DATADIR)/certs
	echo "You still need to install the root certificate in your browser: $(DATADIR)/certs/root.crt" 1>&2

uninstall-cert:
	rm -f $(DESTDIR)$(DATADIR)/certs/root.crt
	rm -f $(DESTDIR)$(DATADIR)/certs/scproxy.key
	rm -f $(DESTDIR)$(DATADIR)/certs/scproxy.chain
	rmdir $(DESTDIR)$(DATADIR)/certs

install-service: system/scproxy.service system/scproxy.socket
	install -d $(DESTDIR)$(SYSTEMDUNITDIR)
	install -m 644 $< $(DESTDIR)$(SYSTEMDUNITDIR)

uninstall-service:
	rm -f $(DESTDIR)$(SYSTEMDUNITDIR)/scproxy.service
	rm -f $(DESTDIR)$(SYSTEMDUNITDIR)/scproxy.socket

system/scproxy.service: system/scproxy.service.in
	sed 's|$$(BINDIR)|$(BINDIR)|g;s|$$(SYSCONFDIR)|$(SYSCONFDIR)|g;s|$$(RUNUSER)|$(RUNUSER)|g' $< >$@

certs/scproxy.chain:
	sh gencerts.sh

clean:
	rm -f system/scproxy.service
	rm -Rf certs/
