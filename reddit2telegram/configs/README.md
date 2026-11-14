# How to setup

## Go and shared configuration

Copy `prod.example.yml` to `prod.yml` and supply credentials locally. From the
repository root use `./r2t consumer` and `./r2t scheduler`. Install the verified
Go binary at `implementations/implementations/go/dist/r2t-go`, or set
`R2T_GO_BINARY`. Configuration and schedule locations remain shared.

Python is retained under `implementations/implementations/python/`.
Its legacy setup utility, for an explicitly selected Python installation, is
available from the repository root with:

```bash
cd implementations/implementations/python/reddit2telegram
../../../../.venv/bin/python utils/maintenance/setup.py
```

## Setup `systemd`

Adjust `/home/r2t/reddit2telegram` in the template to the actual checkout.
The template launches Go directly. Existing services using the old Python-named
entry point remain compatible through its exec wrapper. Switching launchers
does not migrate database indexes or reset uncertain delivery records.

```bash
sudo cp r2t_consumer_app.service /etc/systemd/system/.

sudo systemctl daemon-reload
sudo systemctl enable r2t_consumer_app
sudo systemctl start r2t_consumer_app
sudo systemctl status r2t_consumer_app
```
