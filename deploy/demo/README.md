# The public demo

https://demo.gildehq.com: anyone gets an account with one click, without an email address or a password,
finds a small team, a few tickets and a small wiki beside them, and connects Claude to it. Every night at
04:00 (Amsterdam time) it starts again from the same board and wiki, so nothing a visitor does lasts, and
there is nothing to moderate or keep.

The project in this folder, `demo`, is the demo's own code: the welcome page and its button
([views.py](demo/views.py)), the board and wiki a visitor finds ([seed.py](demo/seed.py)), and the nightly
fresh start (`manage.py reset_demo`). It runs on web1, next to Gilde's own instance
([../web1](../web1/README.md)), but apart from it: its own system user, service and SQLite database.

- **Accounts**: "Try it" makes `visitor-1234`, named Visitor 1234, with no password, puts them in the
  group that may use the board and the wiki, and gives them a welcome ticket that suggests what to try. At
  most 1000 a day. Claude signs in through the same browser session.
- **What a visitor may do**: everything a person on a board or in a wiki may do, deleting tickets, groups
  and pages included. Other visitors see it until the night; the welcome page says so.
- **No mail**: visitors have no address, so notifications go nowhere.
- **Uploads**: up to 5 MB each (Caddy), gone at night with the rest.

| Path | What |
| --- | --- |
| `/srv/gilde-demo/app` | A clone of Gilde's own instance's clone, `/srv/gilde/app`, so it needs no deploy key of its own |
| `/srv/gilde-demo/venv` | The virtualenv, with the packages installed editable from the clone |
| `/srv/gilde-demo/.env` | `DJANGO_SECRET_KEY`, made on the server, and `SENTRY_DSN`; mode 600 |
| `/srv/gilde-demo/data` | The SQLite database |
| `/srv/gilde-demo/static`, `/srv/gilde-demo/media` | `collectstatic`'s output, served by Caddy; the uploads |

The service runs gunicorn on `127.0.0.1:8003` ([gilde-demo.service](gilde-demo.service)), at most 300 MB;
Caddy serves the site ([gilde-demo.caddy](gilde-demo.caddy)); [gilde-demo-reset.timer](gilde-demo-reset.timer)
runs [gilde-demo-reset.service](gilde-demo-reset.service) every night.

## Set up once, as root

```bash
useradd --system --create-home --home-dir /srv/gilde-demo --shell /usr/sbin/nologin gilde-demo
# Caddy, as user caddy, must pass through the home folder to serve /srv/gilde-demo/static
chmod 751 /srv/gilde-demo
install -d -o gilde-demo -g gilde-demo -m 755 /srv/gilde-demo/static
install -d -o gilde-demo -g gilde-demo -m 700 /srv/gilde-demo/data /srv/gilde-demo/media
# the clone of the gilde user's clone, which git trusts only when told to
sudo -u gilde-demo -H git config --global --add safe.directory /srv/gilde/app/.git
sudo -u gilde-demo -H git clone /srv/gilde/app /srv/gilde-demo/app
sudo -u gilde-demo -H python3 -m venv /srv/gilde-demo/venv
# the secret key, never printed
install -o gilde-demo -g gilde-demo -m 600 /dev/null /srv/gilde-demo/.env
echo "DJANGO_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')" > /srv/gilde-demo/.env
# then the deploy steps below, then the board and wiki to start from:
manage reset_demo
cp /srv/gilde-demo/app/deploy/demo/gilde-demo.service /srv/gilde-demo/app/deploy/demo/gilde-demo-reset.* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gilde-demo gilde-demo-reset.timer
cp /srv/gilde-demo/app/deploy/demo/gilde-demo.caddy /etc/caddy/sites/
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy
```

The DNS records, from the laptop, before the first visit to the name:

```bash
hcloud zone add-records --record <web1's IPv4 address> gildehq.com demo A
hcloud zone add-records --record <web1's IPv6 address> gildehq.com demo AAAA
```

## Deploy, as root

After deploying Gilde's own instance ([../web1](../web1/README.md)), whose clone this one pulls from:

```bash
cd /srv/gilde-demo/app
sudo -u gilde-demo -H git pull
sudo -u gilde-demo -H /srv/gilde-demo/venv/bin/pip install -r deploy/demo/requirements.txt
cd deploy/demo
manage() { sudo -u gilde-demo sh -c "set -a; . /srv/gilde-demo/.env; set +a; exec /srv/gilde-demo/venv/bin/python manage.py $*"; }
manage migrate
manage collectstatic --noinput
manage check --deploy
systemctl restart gilde-demo
```

A change to [seed.py](demo/seed.py) shows the next night, or at once with `manage reset_demo`, which signs
every visitor of the day out.

## Logs

`journalctl -u gilde-demo`, and `journalctl -u gilde-demo-reset` for the nights; `systemctl list-timers
gilde-demo-reset` shows when it last and next runs. Errors also go to Sentry, project `gilde`,
environment `demo`, as for Gilde's own instance.
