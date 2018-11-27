# encoding:utf-8

from utils import weighted_random_subreddit

opts = ['r_ImaginaryArchers',
        'r_ImaginaryAssassins',
        'r_ImaginaryAstronauts',
        'r_ImaginaryBoners',
        'r_ImaginaryClerics',
        'r_ImaginaryKnights',
        'r_ImaginaryLovers',
        'r_ImaginaryMythology',
        'r_ImaginaryNobles',
        'r_ImaginaryScholars',
        'r_ImaginarySoldiers',
        'r_ImaginaryVikings',
        'r_ImaginaryWarriors',
        'r_ImaginaryWitches',
        'r_ImaginaryWizards',
        'r_ImaginaryAliens',
        'r_ImaginaryAngels',
        'r_ImaginaryAnimals',
        'r_ImaginaryDwarves',
        'r_ImaginaryElves',
        'r_ImaginaryFaeries',
        'r_ImaginaryHumans',
        'r_ImaginaryImmortals',
        'r_ImaginaryMerfolk',
        'r_ImaginaryOrcs',

        'r_ImaginaryBattlefields',
        'r_ImaginaryCityscapes',
        'r_ImaginaryHellscapes',
        'r_ImaginaryMindscapes',
        'r_ImaginaryPathways',
        'r_ImaginarySeascapes',
        'r_ImaginarySkyscapes',
        'r_ImaginaryStarscapes',
        'r_ImaginaryWeather',
        'r_ImaginaryWildlands',
        'r_ImaginaryWorlds',

        'r_ImaginaryArchitecture',
        'r_ImaginaryCastles',
        'r_ImaginaryDwellings',
        'r_ImaginaryInteriors',
        'r_ImaginaryLibraries',
        'r_ImaginaryTaverns',

        'r_ImaginaryBeasts',
        'r_ImaginaryBehemoths',
        'r_ImaginaryCarnage',
        'r_ImaginaryDemons',
        'r_ImaginaryDragons',
        'r_ImaginaryElementals',
        'r_ImaginaryHorrors',
        'r_ImaginaryHybrids',
        'r_ImaginaryLeviathans',
        'r_ImaginaryMonsterGirls',
        'r_ImaginaryUndead',
        'r_ImaginaryWorldEaters',

        'r_ImaginaryAirships',
        'r_ImaginaryAviation',
        'r_ImaginaryArmor',
        'r_ImaginaryCybernetics',
        'r_ImaginaryCyberpunk',
        'r_ImaginaryFutureWar',
        'r_ImaginaryFuturism',
        'r_ImaginaryMechs',
        'r_ImaginaryPortals',
        'r_ImaginaryRobotics',
        'r_ImaginaryStarships',
        'r_ImaginarySteampunk',
        'r_ImaginaryVehicles',
        'r_ImaginaryVessels',
        'r_ImaginaryWarships',
        'r_ImaginaryWeaponry',

        'r_ImaginaryAww',
        'r_ImaginaryBestOf',
        'r_ImaginaryColorscapes',
        'r_ImaginaryFeels',
        'r_ImaginaryHistory',
        'r_ImaginaryMaps',
        'r_ImaginaryPets',
        'r_ImaginarySliceofLife',
        'r_ImaginaryNetwork',
        'r_ImaginaryTurtleWorlds',
        'r_ImaginaryUnofficial',
        'r_ImaginaryWTF']

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
