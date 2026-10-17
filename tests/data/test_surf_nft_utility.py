"""Reviewed relationships never become rewards merely through token metadata."""
import copy
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import maxpane_dashboard.data.surf_nft_rules.utility as utility


class UtilityTest(unittest.TestCase):
    def setUp(self):
        self.chain = {'chainId': 1, 'address': '0x'+'11'*20, 'codeHash': '0x'+'22'*32,
                      'codePresent': True, 'readBlock': 100, 'readTimestamp': '2026-10-17T00:00:00Z',
                      'reads': {'payment': '0x'+'33'*20}}
        self.rule = {'chainId': 1, 'contract': self.chain['address'], 'codeHash': self.chain['codeHash'],
                     'summary': 'Art paid in EX', 'evidence': [{'label': 'Source', 'url': 'https://example.org/source'}],
                     'readSpecs': [{'name': 'payment', 'type': 'address'}],
                     'tokens': [{'symbol': 'EX', 'name': 'Example', 'addressRead': 'payment', 'roles': ['payment']}],
                     'utility': [{'kind': 'art', 'title': 'Artwork', 'description': 'Collectible artwork.', 'status': 'deployed', 'conditions': 'No yield promised.'}]}
        self.record = {'id':'example','chainId':1,'contractAddress':self.chain['address'],'category':'launched'}

    def apply(self, **kw):
        with patch.object(utility, 'DEPLOYED', [self.rule]):
            return utility.enrich_utility(self.record, kw.get('chain', self.chain))

    def test_exact_binding_and_input_not_mutated(self):
        original = copy.deepcopy(self.record)
        result = self.apply()
        self.assertEqual(result['tokens'][0]['address'], self.chain['reads']['payment'])
        self.assertEqual(result['tokens'][0]['roles'], ['payment'])
        self.assertEqual(result['utility'][0]['kind'], 'art')
        self.assertEqual(self.record, original)

    def test_changed_hash_or_chain_is_unknown(self):
        for changes in ({'codeHash':'0x'+'44'*32}, {'chainId':4663}, {'codePresent':False}):
            result=self.apply(chain={**self.chain,**changes})
            self.assertEqual(result['tokens'], [])
            self.assertEqual(result['utility'][0]['status'], 'unknown')

    def test_missing_dependency_never_reuses_static_address(self):
        result=self.apply(chain={**self.chain,'reads':{}})
        self.assertIsNone(result['tokens'][0]['address'])
        self.assertEqual(result['tokens'][0]['status'], 'unverified-address')
        self.assertNotIn('rewards',result['tokens'][0]['roles'])

    def test_dependency_must_share_block_and_getter_address(self):
        self.rule['tokens'][0]['addressRead']='Vault.asset'
        self.rule['readSpecs']=[{'name':'asset','namespace':'Vault','addressFrom':'vault','type':'address'}]
        self.chain['reads']['vault']='0x'+'55'*20
        dep={'address':self.chain['reads']['vault'],'chainId':1,'readBlock':99,'reads':{'asset':'0x'+'66'*20}}
        self.chain['dependencyReads']={'Vault':dep}
        self.assertIsNone(self.apply()['tokens'][0]['address'])
        dep['readBlock']=100
        self.assertEqual(self.apply()['tokens'][0]['address'],dep['reads']['asset'])
        dep['address']='0x'+'77'*20
        self.assertIsNone(self.apply()['tokens'][0]['address'])

    def test_upcoming_requires_full_objective_and_delivery_commit(self):
        job={'id':'job','objective':'full objective','delivery':{'commit':'abc'}}
        build={**self.rule,'jobId':'job','objectiveSha256':hashlib.sha256(job['objective'].encode()).hexdigest(),
               'deliveryCommit':'abc','tokens':[],'utility':[dict(self.rule['utility'][0],status='implemented')]}
        record={'id':'build','chainId':1,'category':'in_the_making','jobs':[{'id':'job'}]}
        with patch.object(utility,'BUILDS',[build]):
            self.assertEqual(utility.enrich_utility(record,jobs={'job':job})['utility'][0]['status'],'implemented')
            changed={**job,'objective':'truncated'}
            self.assertEqual(utility.enrich_utility(record,jobs={'job':changed})['utility'][0]['status'],'unknown')
            changed={**job,'delivery':{'commit':'other'}}
            self.assertEqual(utility.enrich_utility(record,jobs={'job':changed})['utility'][0]['status'],'unknown')

    def test_read_specs_are_hash_bound(self):
        with patch.object(utility,'DEPLOYED',[self.rule]):
            self.assertEqual(utility.utility_read_specs(self.chain)[0]['name'],'payment')
            self.assertEqual(utility.utility_read_specs({**self.chain,'codeHash':'wrong'}),[])

    def test_unreviewed_hints_preserve_eligibility_and_never_reuse_old_summary(self):
        self.record.update(jobs=[{'id':'job'}], mint={'state':'unknown','publicPrice':None},
                           idmdBenefit={'status':'unknown'}, utilitySummary='NFT staking rewards')
        jobs={'job':{'id':'job','objective':'An NFT game. IDMD holders get a free mint.'}}
        original=copy.deepcopy(self.record)
        with patch.object(utility,'DEPLOYED',[self.rule]):
            result=utility.enrich_utility(self.record,{**self.chain,'codeHash':'changed'},jobs=jobs)
        self.assertEqual({u['kind'] for u in result['utility']},{'game','holder_free_mint'})
        self.assertTrue(all(u['status']=='inferred' for u in result['utility']))
        self.assertEqual(result['utilityReview']['status'],'unreviewed')
        self.assertEqual(result['tokens'],[])
        self.assertEqual(result['mint'],self.record['mint'])
        self.assertEqual(result['idmdBenefit'],self.record['idmdBenefit'])
        self.assertEqual(self.record,original)
        with patch.object(utility,'DEPLOYED',[self.rule]):
            matched=utility.enrich_utility(self.record,self.chain,jobs=jobs)
        self.assertEqual(matched['utility'][0]['status'],'deployed')
        self.assertEqual(matched['utility'][0]['kind'],'art')

    def test_all_reviewed_collections_have_scoped_utility(self):
        self.assertEqual(len(utility.DEPLOYED),20)
        self.assertEqual(len(utility.BUILDS),3)
        for rule in utility.DEPLOYED+utility.BUILDS:
            self.assertTrue(rule['utility'])
            self.assertTrue(rule['evidence'])
            self.assertTrue(rule['summary'])
        pulse=next(r for r in utility.DEPLOYED if r['name']=='Pulse Drone')
        staking=next(u for u in pulse['utility'] if u['kind']=='staking')
        self.assertIn('no rewards',staking['description'].lower())
        self.assertIn('PULSE',staking['title'])
        goblin=next(r for r in utility.DEPLOYED if r['name']=='Goblin Gold')
        self.assertEqual(next(u for u in goblin['utility'] if u['kind']=='game')['status'],'planned')


if __name__=='__main__':
    unittest.main()

"""Conservative, deterministic hints never establish mint eligibility."""
import copy
from pathlib import Path
import sys
import unittest
from maxpane_dashboard.data.surf_nft_rules.hints import infer_utility


class HintTest(unittest.TestCase):
    def setUp(self):
        self.record = {'chainId':1,'contractAddress':'0x'+'11'*20,'jobs':[{'id':'linked'}]}

    def hints(self, text, **extra):
        return infer_utility(self.record, jobs={'linked':{'id':'linked','objective':text}}, **extra)

    def kinds(self, text):
        return {x['kind'] for x in self.hints(text)}

    def test_affirmative_categories_have_evidence(self):
        examples = {'staking':'NFT holders can stake their NFTs to earn rewards.',
                    'defi':'The NFT represents a collateral position in an NFT-backed lending protocol.',
                    'game':'Build an onchain game where NFT characters battle and gain levels.',
                    'governance':'NFT holders vote on treasury proposals through governance.',
                    'access':'This NFT is a membership pass granting token-gated access.',
                    'rewards':'NFT holders share protocol revenue through funded distributions.',
                    'art':'A generative art NFT collection with onchain SVG artwork.',
                    'identity':'NFT identity cards record verifiable wallet credentials.'}
        for kind,text in examples.items():
            with self.subTest(kind=kind):
                found=next(x for x in self.hints(text) if x['kind']==kind)
                self.assertEqual(found['status'],'inferred')
                self.assertIn(text,found['evidence'][0]['snippet'])
                self.assertEqual(found['evidence'][0]['url'],'https://api.imd.fun/jobs/linked')
                self.assertIn('not verified',found['conditions'].lower())

    def test_negated_excluded_examples_and_security_are_not_capabilities(self):
        negatives=['No staking or game mechanics; collectible only.',
                   'Do not implement NFT staking or governance voting.',
                   'Out of scope: NFT staking, game items and lending collateral.',
                   'Example only: an NFT staking game with token-gated access.',
                   'Audit for flash-loan exploits and staking attacks; check governance vulnerabilities.',
                   'Security checklist: test lending collateral manipulation and reward reentrancy.',
                   'NFT staking is not supported.',
                   'NFT staking is outside the scope of this collection.',
                   'Unlike staking games, this collection has no passive rewards.',
                   'Do not add a game. No NFT-holder revenue share.',
                   'The staking adapter is a mock used only for testing.',
                   'Future ideas (not requested): NFT game characters and token-gated access.']
        for text in negatives:
            with self.subTest(text=text):self.assertEqual(self.hints(text),[])

    def test_multiline_scope_headers_suppress_their_items(self):
        text='Out of scope:\n- NFT staking\n- Governance voting\n\nRequirements:\n- Generative NFT artwork.'
        self.assertEqual(self.kinds(text),{'art'})

    def test_holder_free_mint_requires_same_clause_and_nft(self):
        for text in ['IDMD holders can mint one NFT for free.',
                     'IDMD holders get one free mint per wallet.',
                     '1 free mint/claim per wallet for holders of Identity MD NFTs',
                     'Free NFT mint for Identity MD holders.',
                     'IMD token holders may mint a free NFT.',
                     'Existing NFT holders can mint an NFT at no cost.']:
            with self.subTest(text=text):self.assertIn('holder_free_mint',self.kinds(text))
        for text in ['IDMD holders get a free ERC-20 airdrop.',
                     'IDMD holders can mint free ERC20 reward tokens.',
                     'IDMD holders can claim free ERC20 tokens and mint an NFT for 0.1 ETH.',
                     'Fidenza NFT holders mint for free while IDMD holders pay 0.1 ETH.',
                     'Free NFT mint for Genesis holders, excluding IDMD holders.',
                     'Free NFT mint for everyone and IDMD holders may vote.',
                     'NFT holders can mint reward tokens for free.',
                     'IMD holders receive free tokens.',
                     'Free NFT mint for everyone. IDMD holders may vote.',
                     'Free NFT mint for everyone; IDMD holders may vote.',
                     'Only holders can mint NFTs. The game has free rewards.',
                     'NFT holders pay to mint; free token claims are separate.',
                     'IDMD holders cannot mint an NFT for free.']:
            with self.subTest(text=text):self.assertNotIn('holder_free_mint',self.kinds(text))
        self.assertIn('IDMD', next(x for x in self.hints('IDMD holders can mint an NFT for free.') if x['kind']=='holder_free_mint')['title'])
        title=next(x for x in self.hints('IMD token holders can mint an NFT for free.') if x['kind']=='holder_free_mint')['title']
        self.assertIn('IMD token',title)
        self.assertNotIn('IDMD',title)

    def test_generic_financial_words_and_claim_are_insufficient(self):
        self.assertEqual(self.hints('Payments, royalty, yield, claim rewards and the token price.'),[])
        abi=[{'type':'function','name':'claim','inputs':[],'stateMutability':'nonpayable'},
             {'type':'function','name':'royaltyInfo','inputs':[],'stateMutability':'view'},
             {'type':'function','name':'hasStake','inputs':[],'stateMutability':'view'}]
        self.assertEqual(infer_utility(self.record,{'chainId':1,'address':self.record['contractAddress'],'abi':abi}),[])

    def test_abi_staking_requires_actual_paired_mutating_functions(self):
        def f(name,mutability='nonpayable'):return {'type':'function','name':name,'inputs':[{'type':'uint256'}],'stateMutability':mutability}
        chain={'chainId':1,'address':self.record['contractAddress'],'abi':[f('stake'),f('unstake')],'sourceUrl':'https://example.org/contract'}
        result=infer_utility(self.record,chain)
        self.assertEqual({x['kind'] for x in result},{'staking'})
        self.assertIn('stake(uint256)',result[0]['evidence'][0]['signatures'])
        for abi in [[f('stake')],[f('hasStake'),f('unstake')],[f('stake','view'),f('unstake')]]:
            self.assertEqual(infer_utility(self.record,{**chain,'abi':abi}),[])

    def test_erc4626_requires_coherent_interface_not_generic_deposit(self):
        signatures={'asset':[],'totalAssets':[],'convertToShares':['uint256'],'convertToAssets':['uint256'],
                    'deposit':['uint256','address'],'mint':['uint256','address'],
                    'withdraw':['uint256','address','address'],'redeem':['uint256','address','address']}
        abi=[{'type':'function','name':n,'inputs':[{'type':t} for t in ts]} for n,ts in signatures.items()]
        chain={'chainId':1,'address':self.record['contractAddress'],'abi':abi}
        result=infer_utility(self.record,chain)
        self.assertEqual({x['kind'] for x in result},{'defi'})
        self.assertEqual(infer_utility(self.record,{**chain,'abi':[{'type':'function','name':'deposit','inputs':[]}]}),[])

    def test_only_direct_jobs_and_description_is_fallback(self):
        jobs={'unrelated':{'id':'unrelated','objective':'NFT staking game'},'linked':{'id':'linked','objective':'A simple collection.'}}
        record={**self.record,'description':'NFT staking game'}
        self.assertEqual(infer_utility(record,jobs=jobs),[])
        self.assertEqual(infer_utility(self.record,jobs={'unrelated':jobs['unrelated']}),[])
        self.assertIn('game',{x['kind'] for x in infer_utility(record)})

    def test_source_comments_are_evidence_but_imports_and_function_names_are_not_prose(self):
        chain={'chainId':1,'address':self.record['contractAddress'],'pinnedSource':{'url':'https://example.org/pinned',
               'text':'import "./NFTStakingGame.sol";\n/// @notice Generative NFT artwork.\ncontract Art { function claim() external {} }'}}
        result=infer_utility(self.record,chain)
        self.assertEqual({x['kind'] for x in result},{'art'})
        self.assertEqual(result[0]['evidence'][0]['url'],'https://example.org/pinned')

    def test_explicit_defi_long_paragraph_and_unlocked_staking(self):
        self.assertIn('defi',self.kinds('Build a DeFi NFT protocol.'))
        self.assertIn('staking',self.kinds('NFT holders can stake their tokens without a lock.'))
        text='Build a collection with ' + 'a detailed visual specification, '*70 + 'generative NFT artwork.'
        self.assertIn('art',self.kinds(text))
        art=next(x for x in self.hints(text) if x['kind']=='art')
        self.assertIn('generative NFT artwork',art['evidence'][0]['snippet'])

    def test_abandoned_related_jobs_cannot_supply_hints(self):
        for state in ('blocked','failed','cancelled','canceled','rejected','parked','abandoned'):
            record={**self.record,'description':'NFT staking game'}
            jobs={'linked':{'id':'linked','objective':'NFT staking game','state':state}}
            self.assertEqual(infer_utility(record,jobs=jobs),[])

    def test_input_immutability_order_and_size_bounds(self):
        jobs={'linked':{'id':'linked','objective':'NFT staking rewards. An onchain game with NFT characters.'}}
        saved=copy.deepcopy((self.record,jobs))
        first=infer_utility(self.record,jobs=jobs)
        self.assertEqual(first,infer_utility(self.record,jobs=jobs))
        self.assertEqual((self.record,jobs),saved)
        self.assertLessEqual(len(infer_utility(self.record,jobs={'linked':{'id':'linked','objective':'NFT staking. '*50000}})),9)


if __name__=='__main__': unittest.main()
