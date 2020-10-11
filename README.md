reddit2telegram
===============

[![](https://img.shields.io/badge/Telegram-Group-blue.svg)](https://t.me/r_channels)
[![](https://img.shields.io/badge/Telegram-Channel-blue.svg)](https://t.me/reddit2telegram)

Hi there!

These bots just send latest hot submissions from subreddit **/r/%subreddit%** to telegram channel **@r_%subreddit%** hourly. For example [/r/gifs](https://www.reddit.com/r/gifs/) → [@r_gifs](https://t.me/r_gifs).

If you want to obtain your own channel for `/r/%subreddit%`:

1. Create new public telegram channel `@r_%subreddit%`.
2. Add [`@reddit2telegram_bot`](https://t.me/reddit2telegram_bot) as administrator to this channel.
3. Make a pull request to this repo with new script to make posts (use [`reddit2telegram/channels/r_funnny/app.py`](https://github.com/Fillll/reddit2telegram/blob/master/reddit2telegram/channels/r_funny/app.py) as draft).
4. Then I will make it alive :)
5. For any questions do not hesitate to contact me in [@r_channels group](https://t.me/r_channels) or [on reddit](https://www.reddit.com/user/fillll).


If you appreciate it
--------------------

Patreon: [donate](https://www.patreon.com/reddit2telegram)

PayPal: [![](https://www.paypal.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=6EVWBT64BMXZS)

BTC: `1HR9Y8v4aPG5qcQwhiwQu2qHufD6JE5w8c`

ETH: `0x1987b8DFEBc3F52f91b2Af033f616c9D20Fde7ad`


Currently alive channels
------------------------

Complete list of all active channels (more than 500) is available at our channel [@reddit2telegram](https://t.me/reddit2telegram).

---
---
---


Running it
----------

Easiest way is to ask for new channel at [@r_channels](https://t.me/r_channels).

But if you are geek enough then install mongodb, python and setup cron:

```cron
46 * * * * ~/reddit2telegram/auto_update.sh
* * * * * ~/reddit2telegram/reddit2telegram/cron_job.sh
```
