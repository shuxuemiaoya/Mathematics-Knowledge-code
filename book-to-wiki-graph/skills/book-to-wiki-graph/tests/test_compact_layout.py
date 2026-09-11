from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from compact_layout import leaf_box,group_box,pack_boxes


def card(key):
    return leaf_box({'id':key,'type':'text','text':key,'width':280,'height':78})


def edge(left,right,side='right'):
    return {'fromNode':left,'toNode':right,'fromSide':side,'toSide':'left' if side=='right' else 'top'}


class CompactLayoutTests(unittest.TestCase):
    def test_branch_merge_and_downward_application(self):
        boxes=[card(key) for key in 'abcde']
        edges=[edge('a','b'),edge('a','c'),edge('b','d'),edge('c','d'),edge('c','e','bottom')]
        xs,ys=pack_boxes(boxes,edges)
        positions={box.key:(x,y) for box,x,y in zip(boxes,xs,ys)}
        for route in edges:
            a,b=positions[route['fromNode']],positions[route['toNode']]
            self.assertGreaterEqual(b[0]-a[0],420) if route['fromSide']=='right' else self.assertGreaterEqual(b[1]-a[1],188)
        self.assertLessEqual(max(xs),1000)
        self.assertLessEqual(max(ys),600)
        self.assertEqual((xs,ys),pack_boxes(boxes,edges))

    def test_unrelated_nodes_pack_in_two_dimensions_not_a_diagonal(self):
        boxes=[card(str(i)) for i in range(30)]
        xs,ys=pack_boxes(boxes,[])
        area=(max(xs)+280)*(max(ys)+78)
        self.assertLess(area,30*280*78*7)
        self.assertLess(len(set(xs)),15)
        self.assertLess(len(set(ys)),15)

    def test_one_local_timeline_does_not_linearize_other_regions(self):
        boxes=[card(str(i)) for i in range(12)]
        xs,ys=pack_boxes(boxes,[edge('0','1'),edge('1','2')])
        positions={box.key:(x,y) for box,x,y in zip(boxes,xs,ys)}
        self.assertGreaterEqual(positions['1'][0]-positions['0'][0],420)
        self.assertGreaterEqual(positions['2'][0]-positions['1'][0],420)
        self.assertGreater(len(set(ys)),1)
        width,height=max(xs)+280,max(ys)+78
        self.assertLess(max(width/height,height/width),3)

    def test_nested_group_constraints_use_real_endpoint_offsets(self):
        routes=[edge('a','b'),edge('b','c'),edge('a','d','bottom')]
        first=group_box('first','First',[card('a'),card('b')],routes,'g1')
        second=group_box('second','Second',[card('c'),card('d')],routes,'g2')
        parent=group_box('root','Root',[first,second],routes,'g0')
        for route in routes:
            a,b=parent.members[route['fromNode']],parent.members[route['toNode']]
            axis=0 if route['fromSide']=='right' else 1
            self.assertGreater(b[axis],a[axis]+a[axis+2])
        self.assertLess(parent.width*parent.height,3000000)

    def test_direction_conflict_fails_without_silent_edge_reversal(self):
        routes=[edge('a','b'),edge('b','a')]
        with self.assertRaisesRegex(ValueError,'positive cycle'):
            pack_boxes([card('a'),card('b')],routes)
        self.assertEqual(routes[0]['fromNode'],'a')


if __name__=='__main__': unittest.main()
