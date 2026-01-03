Clear mongo log.

```bash
sudo rm /var/log/mongodb/mongod.log
```

Check disk usage:
```bash
ncdu /
```

## r2t_consumer_app.service
Systemd unit for the task queue consumer.

Unit file location:
```
/etc/systemd/system/r2t_consumer_app.service
```

Unit file contents:
```ini
[Unit]
Description=r2t_consumer

[Service]
WorkingDirectory=/root/reddit2telegram/reddit2telegram
ExecStart=/root/reddit2telegram/.venv/bin/python task_queue_consumer.py --config configs/prod.yml
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Common commands:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now r2t_consumer_app.service
sudo systemctl status --no-pager r2t_consumer_app.service
```
