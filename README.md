reddit2telegram
===============

Hi there!

These bots just send latest hot submissions from subreddit **/r/%subreddit%** to telegram channel **@r_%subreddit%** hourly. For example [/r/gifs](https://www.reddit.com/r/gifs/) → [@r_gifs](https://telegram.me/r_gifs).

If you want to obtain your own channel for `/r/%subreddit%`:

1. Create new public telegram channel `@r_%subreddit%`.
2. Add `@reddit2telegram_bot` as administrator to this channel.
3. Make a pull request to this repo with new script to make posts (use `/channels/r_jokes/app.py` as draft).
4. Then I will make it alive :)
5. For any questions do not hesitate to contact me in [this group](https://telegram.me/r_channels) or [on reddit](https://www.reddit.com/user/fillll).


Currently alive channels
------------------------

1. [@r_gifs](https://telegram.me/r_gifs)
2. [@r_jokes](https://telegram.me/r_jokes)
3. [@r_funny](https://telegram.me/r_funny)
4. [@DataScientology](https://telegram.me/datascientology)
5. [@asiangirlsbeingcute](https://telegram.me/asiangirlsbeingcute)
6. [@r_behindthegifs](https://telegram.me/r_behindthegifs)
7. [@pythondaily](https://telegram.me/pythondaily)
8. [@r_unexpected](https://telegram.me/r_unexpected)
9. ... be the next one ...


If you appreciate it
--------------------

[![](https://www.paypal.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=6EVWBT64BMXZS)


Running it
----------
Easiest way is to do it with docker. It will set up the mongo database dependency.

#### Config
Make your copy of `prod.yml` and `imgur.yml`. 
```shell
cp prod.yml.example prod.yml
cp imgur.yml.example imgur.yml
```

Now edit the files, replacing the values with real ones.

> Note: When using docker, `db_host: "mongo"` must be set in `prod.yml`. 
 
#### Launching
```shell
docker-compose up -d
```
- `-d` is detach. Leave out to see output.

#### Changing code
```shell
docker-compose up reddit2tg --build
```
Assuming you already started `mongo` in detached mode (above).
This rebuilds the reddit2tg image and launches it.
- `reddit2tg`: the service name of the bot part (as opposed to the database `mongo`)
- `--build` if you changed code and need a new build version

#### Note
The `reddit2tg` docker image is terminating pretty quickly as the python script was made for a cron script.
Currently you have to either start the container over and over again (`docker-compose up -d reddit2tg`)
or finally write a cron like script in the docker container. (Send a PR please!)
