# encoding:utf-8

from utils import weighted_random_subreddit

opts = ['ImaginaryArtisans',
        'ImaginaryBikers',
        'ImaginaryClerics',
        'ImaginaryCharacters',
        'ImaginaryCowboys',
        'ImaginaryCultists',
        'ImaginaryDruids',
        'ImaginaryFamilies',
        'ImaginaryGatherings',
        'ImaginaryLesbians',
        'ImaginaryMaidens',
        'ImaginaryMeIRL',
        'ImaginaryMen',
        'ImaginaryMerchants',
        'ImaginaryMonsterBoys',
        'ImaginaryNatives',
        'ImaginaryNinjas',
        'ImaginaryNomads',
        'ImaginaryPirates',
        'ImaginaryPolice',
        'ImaginaryPunks',
        'ImaginarySlavery',
        'ImaginaryVikings',
        'ImaginaryVillains',

        # [Races]
        'ImaginaryAliens',
        'ImaginaryCentaurs',
        'ImaginaryGiants',
        'ImaginaryGoblins',
        'ImaginaryGnomes',
        'ImaginaryTrolls',

        # [Landscapes]
        'ImaginaryAutumnscapes',
        'ImaginaryBodyscapes',
        'ImaginaryLandscapes',
        'ImaginaryNightscapes',
        'ImaginarySpringscapes',
        'ImaginarySummerscapes',
        'ImaginaryWaterscapes',
        'ImaginaryWinterscapes',

        # [Nature]
        'ImaginaryCanyons',
        'ImaginaryCaves',
        'ImaginaryDeserts',
        'ImaginaryForests',
        'ImaginaryGardens',
        'ImaginaryGlaciers',
        'ImaginaryIslands',
        'ImaginaryLakes',
        'ImaginaryMountains',
        'ImaginaryRivers',
        'ImaginarySwamps',
        'ImaginaryTrees',
        'ImaginaryVolcanoes',
        'ImaginaryWaterfalls',

        # [Architecture]
        'ImaginaryAsylums',
        'ImaginaryFactories',
        'ImaginaryMonuments',
        'ImaginaryPrisons',
        'ImaginaryRuins',
        'ImaginaryStatues',
        'ImaginaryTaverns',
        'ImaginaryTemples',
        'ImaginaryTowers',
        'ImaginaryVillages',
        'ImaginaryWalls',

        # [Monsters]
        'ImaginaryCrawlers',
        'ImaginaryDinosaurs',
        'ImaginaryMonsters',
        'ImaginarySpirits',
        'ImaginaryUnicorns',
        'ImaginaryVampires',
        'ImaginaryWerewolves',

        # [Technology]
        'ImaginaryAetherpunk',
        'ImaginaryAirships',
        'ImaginaryAviation',
        'ImaginaryDerelicts',
        'ImaginaryDieselpunk',
        'ImaginaryTechnology',
        'ImaginaryTrains',
        'ImaginaryVessels',
        'ImaginaryScience',
        'ImaginaryWarships',

        # [Fandoms]
        'ImaginaryAnime',
        'ImaginaryArrakis',
        'ImaginaryBakerSt',
        'ImaginaryCosmere',
        'ImaginaryDarkSouls',
        'ImaginaryDC',
        'ImaginaryDisney',
        'ImaginaryFederation',
        'ImaginaryEquestria',
        'ImaginaryGallifrey',
        'ImaginaryGaming',
        'ImaginaryGolarion',
        'ImaginaryGotham',
        'ImaginaryHalo',
        'ImaginaryHogwarts',
        'ImaginaryMassEffect',
        'ImaginaryMinecraft',
        'ImaginaryMutants',
        'ImaginaryNarnia',
        'ImaginaryNecronomicon',
        'ImaginaryNewNewYork',
        'ImaginaryOoo',
        'ImaginaryOverwatch',
        'ImaginaryShadowrun',
        'ImaginarySpringfield',
        'ImaginaryStarfinder',
        'ImaginaryStephenKing',
        'ImaginarySunnydale',
        'ImaginaryVerse',
        'ImaginaryWestWorld',

        # [Misc]
        'ImaginaryAdrenaline',
        'ImaginaryAgriculture',
        'ImaginaryAlchemy',
        'ImaginaryAnimals',
        'ImaginaryBooks',
        'ImaginaryExplosions',
        'ImaginaryFashion',
        'ImaginaryFood',
        'ImaginaryHistory',
        'ImaginaryIcons',
        'ImaginaryMovies',
        'ImaginaryPolice',
        'ImaginaryPolitics',
        'ImaginaryPropaganda',
        'ImaginaryScars',
        'ImaginarySliceOfBread',
        'ImaginarySports',
        'ImaginaryTattoos',
        'ImaginaryWTF',
        ]

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
