# encoding:utf-8

from utils import weighted_random_subreddit

opts = ['ImaginaryArchers',
        'ImaginaryAssassins',
        'ImaginaryAstronauts',
        'ImaginaryBoners',
        'ImaginaryClerics',
        'ImaginaryKnights',
        'ImaginaryLovers',
        'ImaginaryMythology',
        'ImaginaryNobles',
        'ImaginaryScholars',
        'ImaginarySoldiers',
        'ImaginaryVikings',
        'ImaginaryWarriors',
        'ImaginaryWitches',
        'ImaginaryWizards',
        'ImaginaryAliens',
        'ImaginaryAngels',
        'ImaginaryAnimals',
        'ImaginaryDwarves',
        'ImaginaryElves',
        'ImaginaryFaeries',
        'ImaginaryHumans',
        'ImaginaryImmortals',
        'ImaginaryMerfolk',
        'ImaginaryOrcs',

        'ImaginaryBattlefields',
        'ImaginaryCityscapes',
        'ImaginaryHellscapes',
        'ImaginaryMindscapes',
        'ImaginaryPathways',
        'ImaginarySeascapes',
        'ImaginarySkyscapes',
        'ImaginaryStarscapes',
        'ImaginaryWeather',
        'ImaginaryWildlands',
        'ImaginaryWorlds',

        'ImaginaryArchitecture',
        'ImaginaryCastles',
        'ImaginaryDwellings',
        'ImaginaryInteriors',
        'ImaginaryLibraries',
        'ImaginaryTaverns',

        'ImaginaryBeasts',
        'ImaginaryBehemoths',
        'ImaginaryCarnage',
        'ImaginaryDemons',
        'ImaginaryDragons',
        'ImaginaryElementals',
        'ImaginaryHorrors',
        'ImaginaryHybrids',
        'ImaginaryLeviathans',
        'ImaginaryMonsterGirls',
        'ImaginaryUndead',
        'ImaginaryWorldEaters',

        'ImaginaryAirships',
        'ImaginaryAviation',
        'ImaginaryArmor',
        'ImaginaryCybernetics',
        'ImaginaryCyberpunk',
        'ImaginaryFutureWar',
        'ImaginaryFuturism',
        'ImaginaryMechs',
        'ImaginaryPortals',
        'ImaginaryRobotics',
        'ImaginaryStarships',
        'ImaginarySteampunk',
        'ImaginaryVehicles',
        'ImaginaryVessels',
        'ImaginaryWarships',
        'ImaginaryWeaponry',

        'ImaginaryAww',
        'ImaginaryBestOf',
        'ImaginaryColorscapes',
        'ImaginaryFeels',
        'ImaginaryHistory',
        'ImaginaryMaps',
        'ImaginaryPets',
        'ImaginarySliceofLife',
        'ImaginaryNetwork',
        'ImaginaryTurtleWorlds',
        'ImaginaryUnofficial',
        'ImaginaryWTF']

weight = 1. / len(opts)

# Subreddit that will be a source of content
subreddit = weighted_random_subreddit({k: weight for k in opts})

t_channel = '@r_imaginary_network'


# r_imaginary_wastelands


def send_post(submission, r2t):
    return r2t.send_simple(submission,
                           min_upvotes_limit=20,
                           text=False,
                           gif=False,
                           img=True,
                           album=False,
                           other=False
                           )
