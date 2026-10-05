import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from postmatch_impect.title_race_views import fixture_perspective, trajectory, form_games

class PerspectiveTests(unittest.TestCase):
    def test_home_away_probabilities_are_reversed_not_teams(self):
        f={'Local':'Al Ain','Visitante':'Al Wasl','P(local) %':50,'P(empate) %':20,'P(visitante) %':30}
        self.assertEqual(fixture_perspective(f,'Al Wasl'),{'venue':'Fuera','win':30,'draw':20,'loss':50})
        self.assertEqual(fixture_perspective(f,'Al Ain'),{'venue':'En casa','win':50,'draw':20,'loss':30})
        self.assertEqual(f['Local'],'Al Ain')
        with self.assertRaises(ValueError):fixture_perspective(f,'Al Jazira')

    def test_jornadas_and_away_result(self):
        squads={1:{'id':1,'name':'A'},2:{'id':2,'name':'B'}}
        data={'matches':[
            {'id':1,'homeSquadId':1,'awaySquadId':2,'matchDay':{'index':0},'scheduledDate':'2026-08-01','goals':{'home':{'fullTime':2},'away':{'fullTime':0}}},
            {'id':2,'homeSquadId':2,'awaySquadId':1,'matchDay':{'index':1},'scheduledDate':'2026-08-08','goals':{'home':{'fullTime':1},'away':{'fullTime':1}}},
            {'id':3,'homeSquadId':1,'awaySquadId':2,'matchDay':{'index':2}}]}
        rows=trajectory(data,[1,2],squads)
        self.assertEqual([(r['Jornada'],r['Puntos']) for r in rows if r['Equipo']=='A'],[(0,0),(1,3),(2,4)])
        away=form_games(data,2,'Fuera')
        self.assertEqual([(m['gf'],m['ga'],m['outcome']) for m in away],[(0,2,'D')])
        self.assertEqual(len(form_games(data,1,'En casa')),1)

if __name__=='__main__':unittest.main()
