# DataGroceries on web1

DataGroceries' own instance, at https://hq.datagroceries.com: Jasper's tickets on the board and the wiki,
with Claude connected. The first installation outside the example project, on PostgreSQL. It runs on web1, a small
Hetzner Cloud server with Ubuntu 26.04, next to other sites, behind Caddy. The server itself is described
in its own documentation, which is not public; here is only what is DataGroceries'. `ssh web1` below is the
server, as an SSH alias.

| Path | What |
| --- | --- |
| `/srv/gilde/app` | A clone of this repository, over HTTPS, as it is public |
| `/srv/gilde/venv` | The virtualenv, with the packages installed editable from the clone |
| `/srv/gilde/.env` | `DJANGO_SECRET_KEY`, made on the server; `EMAIL_HOST` and `EMAIL_HOST_USER`, the SMTP server and DataGroceries' mailbox; `EMAIL_HOST_PASSWORD`, the mailbox's password, put there by Jasper; `DG_BOARD_GITHUB_WEBHOOK_SECRET`, shared with the repository's webhook; and `SENTRY_DSN`; mode 600 |
| `/srv/gilde/static`, `/srv/gilde/media` | `collectstatic`'s output, served by Caddy; uploaded attachments |
| `/srv/gilde/backups` | The nightly dumps, 14 days |
| PostgreSQL 18, database `datagroceries` | Owned by the role `gilde`, reached through the socket as the system user `gilde`, without a password |

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
sudo -u postgres createdb --owner gilde datagroceries
sudo -u gilde -H git clone https://github.com/datagroceries/django-dg.git /srv/gilde/app
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
hcloud zone add-records --record <web1's IPv4 address> datagroceries.com hq A
hcloud zone add-records --record <web1's IPv6 address> datagroceries.com hq AAAA
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
superusers may use the board until a group gets its permission (`dg.W003`).

## The move to DataGroceries (7 November 2026)

Gilde became DataGroceries (docs/decisions.md). The data moved from the database `gilde`, on the old app
labels, to `datagroceries`: dumped with the old code (`dumpdata --natural-foreign --natural-primary`, without
content types, permissions, sessions and the admin log), relabelled `gilde_*` → `dg_*`, loaded with
`SIMPLE_HISTORY_ENABLED=False` (or loading a ticket writes a history record of its own over the dumped ones),
the sequences reset with `sqlsequencereset`, and every model's count compared. The settings in `.env` went
from `GILDE_*` to `DG_*`.

Afterwards, the same day: Claude was reconnected to hq.datagroceries.com, as OAuth clients registered on the
old address no longer signed in there (the address they check ends in `/dg/` now). Then the old database
`gilde`, the dumps and the backup from before the move were removed, and so were gilde.datagroceries.com and
gildehq.com, with their DNS records. The server's own names (the user, folders and services) stay `gilde`.

## Backups

[gilde-backup.timer](gilde-backup.timer) runs [gilde-backup.service](gilde-backup.service) at 03:30: a
`pg_dump` in PostgreSQL's custom format to `/srv/gilde/backups`, kept 14 days. They guard against a
mistake, not against losing the server. To restore one, into an empty database:

```bash
sudo -u gilde pg_restore --clean --if-exists --dbname datagroceries /srv/gilde/backups/dg-<date>.dump
```

## Logs

`journalctl -u gilde` (Django's warnings and errors, and the notifications while there is no mail
password), `journalctl -u gilde-backup` and `journalctl -u caddy`.

Errors also go to Sentry, project `gilde` in the organisation `datagroceries` (US region), environment
`production`, through `SENTRY_DSN` in `/srv/gilde/.env`: without request bodies, IP addresses or user
details.

## GitHub

Commits on `main`, branches and pull requests that name a `G-` ticket show in its Code panel (the board's
README, "GitHub"). The repository has a webhook to `https://hq.datagroceries.com/dg/board/github/webhook/`:
JSON, the events Pushes, Pull requests and Branch or tag creation, and the secret that is
`DG_BOARD_GITHUB_WEBHOOK_SECRET` in `/srv/gilde/.env`. It was made with a fresh secret written to both
at once, never printed. The webhook's Recent deliveries on GitHub show each delivery and the answer; one
refused while the site was down or not yet deployed can be redelivered there.

There is no `DG_BOARD_GITHUB_TOKEN`: only `manage.py backfill_github` needs one, to read history from
before the webhook, and the repository has none that names a ticket.

## Mail

Notifications go out over SMTP through Hetzner's webhosting, from a mailbox of DataGroceries' own, which only
sends (`hq/settings.py`). The server and the mailbox are in `/srv/gilde/.env` as `EMAIL_HOST` and
`EMAIL_HOST_USER`, so that this public repository does not name them; Jasper's private notes have them.
The settings switch to SMTP once `EMAIL_HOST_PASSWORD` is there too, typed on the server and never
printed. Between single quotes, so that both systemd and the shell take characters such as `$` as they
are; the password must hold no `'`:

```bash
ssh -t web1 'read -rs -p "Password of the DataGroceries mailbox: " p && echo && printf "EMAIL_HOST_PASSWORD='"'"'%s'"'"'\n" "$p" >> /srv/gilde/.env && systemctl restart gilde'
```

Then a test, to an address of your own:

```bash
ssh web1 'cd /srv/gilde/app/deploy/web1 && sudo -u gilde sh -c "set -a; . /srv/gilde/.env; set +a; exec /srv/gilde/venv/bin/python manage.py sendtestemail you@example.com"'
```
