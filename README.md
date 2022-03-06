reddit2telegram
===============

[![](https://img.shields.io/badge/Telegram-Group-blue.svg)](https://t.me/r_channels)
[![](https://img.shields.io/badge/Telegram-Channel-blue.svg)](https://t.me/reddit2telegram)

Hi there!

These bots just send latest hot submissions from subreddit **/r/%subreddit%** to telegram channel **@r_%subreddit%** hourly. For example [/r/gifs](https://www.reddit.com/r/gifs/) → [@r_gifs](https://t.me/r_gifs).

If you want to obtain your own channel for `/r/%subreddit%`:

1. Create new public telegram channel `@r_%subreddit%`.
2. Add [`@reddit2telegram_bot`](https://t.me/reddit2telegram_bot) as administrator to this channel.
3. Make a pull request to this repo with new script to make posts (use [`reddit2telegram/channels/r_funnny/app.py`](https://github.com/Fillll/reddit2telegram/blob/master/reddit2telegram/channels/r_funny/app.py) as draft), and the tags related (create a tags.txt containing at least 3 tags, separated by spaces and starting with #).
4. Then I will make it alive :)
5. For any questions do not hesitate to contact me in [@r_channels](https://t.me/r_channels) group.


If you appreciate it
--------------------

Patreon: [donate](https://www.patreon.com/reddit2telegram)

BTC: `3DydQjRPaykiapdeab6ABAhB5f2JazwaRD`

ETH: `0xc313B7bEbFc605cC5B50fa97902506404D58df80`

LTC: `MT3gDG9VZvSDmsRexQ3k19JLxhDSCjf45T`


Currently alive channels
------------------------

Complete list of all active channels (more than 700) is available at our channel [@reddit2telegram](https://t.me/reddit2telegram).


This is a pet-project 🐶
------------------------

Which means you really shouldn't expect much from it. I wrote it over the weekend to solve my own pain. No state-of-art kubernetes bullshit, no architecture patterns, even no tests at all. It's here just to show people what a pet-project might look like.

This code has been written for fun, not for business. There is usually a big difference. Like between riding a bike on the streets and cycling in the wild for fun :)

_© from [infomate.club](https://github.com/vas3k/infomate.club)_



Running it
----------

Easiest way is to ask for new channel at [@r_channels](https://t.me/r_channels). Or follow the manual as stated above. :)

But if you are geek enough then install mongodb, ffmpeg, python and setup cron:

```cron
46 * * * * ~/reddit2telegram/auto_update.sh
* * * * * ~/reddit2telegram/reddit2telegram/cron_job.sh
```
