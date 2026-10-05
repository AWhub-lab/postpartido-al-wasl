import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from postmatch_impect.title_race import forecast, complete_calendar, validate, match_xg, poisson_outcomes, isr_at


def data():
    return {'iteration':{'id':1,'season':'26/27'},'squads':[{'id':1,'name':'A'},{'id':2,'name':'B'}], 'fetched_at':'2026-10-05', 'matches':[
        {'id':1,'homeSquadId':1,'awaySquadId':2,'goals':{'home':{'fullTime':2},'away':{'fullTime':0}}},
        {'id':2,'homeSquadId':2,'awaySquadId':1,'goals':{'home':{'fullTime':0},'away':{'fullTime':1}}}]}

class ForecastTests(unittest.TestCase):
    def test_finished_champion(self):
        r=forecast(data(),simulations=1000)
        self.assertEqual(r['summary'][0]['Título aprox. %'],100)
        self.assertEqual(r['summary'][0]['Puntos previstos'],6)
        self.assertEqual(r['fixtures'],[])

    def test_ties_are_explicit(self):
        d=data()
        for m in d['matches']:
            m['goals']={'home':{'fullTime':0},'away':{'fullTime':0}}
        r=forecast(d,simulations=1000)
        for row in r['summary']:
            self.assertEqual(row['Título aprox. %'],50)
            self.assertEqual(row['Primero en solitario %'],0)
            self.assertEqual(row['Primero o empatado %'],100)

    def test_missing_calendar_and_duplicates(self):
        d=data();d['matches'].pop()
        with self.assertRaises(ValueError):validate(d)
        c=complete_calendar(d)
        self.assertEqual(len(d['matches']),1)
        self.assertEqual(c['inferred_fixtures'],1)
        r=forecast(c,simulations=1000)
        self.assertAlmostEqual(sum(x['Título aprox. %'] for x in r['summary']),100,places=1)
        for row in r['summary']:
            self.assertGreaterEqual(row['P10'],row['Puntos'])
            self.assertLessEqual(row['P90'],row['Puntos']+3*row['Pendientes'])
        d['matches'].append(copy.deepcopy(d['matches'][0]))
        with self.assertRaises(ValueError):complete_calendar(d)

    def test_reproducible_and_no_future_leak(self):
        d=data();d['matches'][1].pop('goals')
        future=data();future['iteration']={'id':2,'season':'27/28'}
        r=forecast(d,simulations=1000); s=forecast(d,[future],simulations=1000)
        self.assertEqual(r['summary'],s['summary'])
        self.assertEqual(r['input_hash'],s['input_hash'])
        d['fetched_at']='later'
        self.assertEqual(r['input_hash'],forecast(d,simulations=1000)['input_hash'])

    def test_incomplete_historical_excluded(self):
        old=data();old['iteration']={'id':3,'season':'25/26'};old['matches'][1].pop('goals')
        self.assertEqual(forecast(data(),[old],simulations=1000)['inputs']['historical'],[])

    def test_xg_changes_strength_and_hash(self):
        d=data();d['matches'][1].pop('goals')
        proc={1:{'1':{'home':{'xg':0.3},'away':{'xg':2.5}}}}
        plain=forecast(d,simulations=2000); with_xg=forecast(d,simulations=2000,process=proc)
        self.assertNotEqual(plain['input_hash'],with_xg['input_hash'])
        a=lambda r:next(x for x in r['summary'] if x['id']==1)['Ataque']
        self.assertLess(a(with_xg),a(plain))
        self.assertEqual(match_xg(proc[1],1),(0.3,2.5))
        self.assertIsNone(match_xg(proc[1],2))

    def test_title_curve_is_monotonic_and_outcomes_sum(self):
        d=data();d['matches'][1].pop('goals')
        r=forecast(d,simulations=2000)
        c=[x['Título aprox. %'] for x in r['curves'] if x['id']==1]
        self.assertEqual(c,sorted(c))
        self.assertAlmostEqual(sum(poisson_outcomes(1.4,1.1,15)),1,places=4)

    def test_isr_prior_lifts_better_rated_team_without_peeking(self):
        d=data();d['matches'][1].pop('goals')
        ratings={'1':[['2026-08-01',0.5],['2026-12-01',0.9]],'2':[['2026-08-01',0.7]]}
        self.assertEqual(isr_at(ratings,1,'2026-10-05'),0.5)
        self.assertIsNone(isr_at(ratings,1,'2026-07-01'))
        r=forecast(d,simulations=2000,ratings=ratings,isr_date='2026-10-05',isr_k=3)
        base=forecast(d,simulations=2000)
        att=lambda r,i:next(x for x in r['summary'] if x['id']==i)['Ataque']
        self.assertLess(att(r,1),att(base,1)); self.assertGreater(att(r,2),att(base,2))

if __name__=='__main__':unittest.main()
