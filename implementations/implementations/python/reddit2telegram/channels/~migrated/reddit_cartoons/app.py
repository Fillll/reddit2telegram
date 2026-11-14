#encoding:utf-8

subreddit = 'animation+cartoons+BigHero6+ducktales+00scartoons+calvinandhobbes+gravityfalls+rickandmortytheory+ArcherFX+CartoonTalk+rickandmortyGIFs+ClarenceCartoon+regularshow+charactercrossovers+CartoonPhysics+FinalSpace+Cartoongifs+nostalgia+animationgifs+BoltTheSuperdog+americandad+disney+TheSimpsons+southpark+CartoonLogicGifs+zootopia+KingOfTheHill+rickandmorty+familyguy+80scartoons+futurama+rickandmorty_C137+90scartoons+peanuts+disneyoutofcontext+clarence+BobsBurgers+SimpsonsGifs+BikiniBottomTwitter+Toonami+adventuretime+CartoonNetwork+DarkwingDuck'
t_channel = '@reddit_cartoons'


def send_post(submission, r2t):
    return r2t.send_simple(submission,
        check_dups=True,
        text='{title}\n\n{self_text}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}\n{channel}',
        other='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}\n{channel}',
        album='{title}\n{link}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}\n{channel}',
        gif='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}\n{channel}',
        img='{title}\n\n{upvotes} upvotes\n/r/{subreddit_name}\n{short_link}\n{channel}'
    )
