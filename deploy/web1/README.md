# Gilde on web1

Gilde's own instance, at https://gilde.datagroceries.com: Jasper's tickets on the board, with Claude
connected. The first installation outside the example project, on PostgreSQL. It runs on web1, a small
Hetzner Cloud server with Ubuntu 26.04, next to other sites, behind Caddy. The server itself is described
in its own documentation, which is not public; here is only what is Gilde's. `ssh web1` below is the
server, as an SSH alias.

| Path | What |
| --- | --- |
| `/srv/gilde/app` | A clone of this repository, through a read-only GitHub deploy key (`/srv/gilde/.ssh/id_ed25519`, "web1 (read-only)" under the repository's Deploy keys) |
| `/srv/gilde/venv` | The virtualenv, with the packages installed editable from the clone |
| `/srv/gilde/.env` | `DJANGO_SECRET_KEY`, made on the server; `EMAIL_HOST` and `EMAIL_HOST_USER`, the SMTP server and Gilde's mailbox; and `EMAIL_HOST_PASSWORD`, the mailbox's password, put there by Jasper; mode 600 |
| `/srv/gilde/static`, `/srv/gilde/media` | `collectstatic`'s output, served by Caddy; uploaded attachments |
| `/srv/gilde/backups` | The nightly dumps, 14 days |
| PostgreSQL 18, database `gilde` | Owned by the role `gilde`, reached through the socket as the system user `gilde`, without a password |

The project in this folder, `hq`, is all the code of its own: settings, URLs and WSGI. The service runs
gunicorn on `127.0.0.1:8002` ([gilde.service](gilde.service)); Caddy serves the site
([gilde.caddy](gilde.caddy)).

## Set up once, as root

```bash
apt-get -y install postgresql
useradd --system --create-home --home-dir /srv/gilde --shell /usr/sbin/nologin gilde
# Caddy, as user caddy, must pass through the home folder to serve /srv/gilde/static
chmod 751 /srv/gilde
install -d -o gilde -g gilde -m 755 /srv/gilde/static
install -d -o gilde -g gilde -m 750 /srv/gilde/media
install -d -o gilde -g gilde -m 700 /srv/gilde/backups
sudo -u postgres createuser gilde
sudo -u postgres createdb --owner gilde gilde
sudo -u gilde -H ssh-keygen -t ed25519 -N '' -C 'web1 gilde deploy key' -f /srv/gilde/.ssh/id_ed25519
# add the .pub as a read-only deploy key, from the laptop (the organisation must allow deploy keys):
#   gh repo deploy-key add <file> --repo gildehq/gilde --title 'web1 (read-only)'
# GitHub's host key, checked against `gh api meta --jq .ssh_key_fingerprints`
ssh-keyscan -t ed25519 github.com | sudo -u gilde tee /srv/gilde/.ssh/known_hosts
sudo -u gilde -H git clone git@github.com:gildehq/gilde.git /srv/gilde/app
sudo -u gilde -H python3 -m venv /srv/gilde/venv
# the secret key, never printed
install -o gilde -g gilde -m 600 /dev/null /srv/gilde/.env
echo "DJANGO_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" > /srv/gilde/.env
# then the deploy steps below, then:
cp /srv/gilde/app/deploy/web1/gilde.service /srv/gilde/app/deploy/web1/gilde-backup.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gilde gilde-backup.timer
cp /srv/gilde/app/deploy/web1/gilde.caddy /etc/caddy/sites/
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy
```

The DNS records, from the laptop. Ask for the new name only after making them: a resolver that was
asked before, such as a home router, keeps its "no such name" for up to an hour (the zone's negative
TTL), while Claude's servers find it at once.

```bash
hcloud zone add-records --record <web1's IPv4 address> datagroceries.com gilde A
hcloud zone add-records --record <web1's IPv6 address> datagroceries.com gilde AAAA
```

Jasper's account, with a password typed on the server and never stored anywhere else:

```bash
ssh -t web1 'cd /srv/gilde/app/deploy/web1 && sudo -u gilde sh -c "set -a; . /srv/gilde/.env; set +a; exec /srv/gilde/venv/bin/python manage.py createsuperuser"'
```

## Deploy, as root

```bash
cd /srv/gilde/app
sudo -u gilde -H git pull
sudo -u gilde -H /srv/gilde/venv/bin/pip install -r deploy/web1/requirements.txt
cd deploy/web1
# manage.py as the gilde user, with the secret key from the .env file only that user can read. Not
# sudo -E: Ubuntu 26.04's sudo does not pass the environment on.
manage() { sudo -u gilde sh -c "set -a; . /srv/gilde/.env; set +a; exec /srv/gilde/venv/bin/python manage.py $*"; }
manage migrate
manage collectstatic --noinput
manage check --deploy
systemctl restart gilde
```

The service and Caddy files are copied by hand when they change. `check --deploy` warns that only
superusers may use the board until a group gets its permission (`gilde.W003`).

## Backups

[gilde-backup.timer](gilde-backup.timer) runs [gilde-backup.service](gilde-backup.service) at 03:30: a
`pg_dump` in PostgreSQL's custom format to `/srv/gilde/backups`, kept 14 days. They guard against a
mistake, not against losing the server. To restore one, into an empty database:

```bash
sudo -u gilde pg_restore --clean --if-exists --dbname gilde /srv/gilde/backups/gilde-<date>.dump
```

## Logs

`journalctl -u gilde` (Django's warnings and errors, and the notifications while there is no mail
password), `journalctl -u gilde-backup` and `journalctl -u caddy`.

## Mail

Notifications go out over SMTP through Hetzner's webhosting, from a mailbox of Gilde's own, which only
sends (`hq/settings.py`). The server and the mailbox are in `/srv/gilde/.env` as `EMAIL_HOST` and
`EMAIL_HOST_USER`, so that this public repository does not name them; Jasper's private notes have them.
The settings switch to SMTP once `EMAIL_HOST_PASSWORD` is there too, typed on the server and never
printed. Between single quotes, so that both systemd and the shell take characters such as `$` as they
are; the password must hold no `'`:

```bash
ssh -t web1 'read -rs -p "Password of the Gilde mailbox: " p && echo && printf "EMAIL_HOST_PASSWORD='"'"'%s'"'"'\n" "$p" >> /srv/gilde/.env && systemctl restart gilde'
```

Then a test, to an address of your own:

```bash
ssh web1 'cd /srv/gilde/app/deploy/web1 && sudo -u gilde sh -c "set -a; . /srv/gilde/.env; set +a; exec /srv/gilde/venv/bin/python manage.py sendtestemail you@example.com"'
```
