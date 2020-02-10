#encoding:utf-8

subreddit = 'Chainlink+Vechain+FetchAI_Community+perlin+Qtum+NEO+hashgraph+IoTeX+elrondnetwork+Aeternity+loopringorg+waltonchain+nebulas+IOStoken+NavCoin+viacoin+skycoin+MoedaBanking+WabiToken+EnjinCoin+OntologyNetwork+PolymathNetwork+insolar+nexusearth+zcoin+zilliqa+quarkchainio+tezos+Neblio+helloicon+ArkEcosystem+kybernetwork+0xProject+BATProject+SysCoin+omise_go+pivx+civicplatform+factom+nem+Stellar+Ripple+Wavesplatform+statusim+Ardor+stratisplatform+GolemProject+komodoplatform+storj+vergecurrency+eos+siacoin'
t_channel = '@cryptoinstantnews2'


def send_post(submission, r2t):
    return r2t.send_simple(submission)
