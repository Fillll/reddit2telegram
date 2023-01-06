# How to setup

## Run `setup.py`

it takes care of indexes.

```bash
python utils/setup.py
```

## Setup `systemd`

```bash
sudo cp r2t_consumer_app.service /etc/systemd/system/.

sudo systemctl daemon-reload
sudo systemctl enable r2t_consumer_app
sudo systemctl start r2t_consumer_app
sudo systemctl status r2t_consumer_app
```
