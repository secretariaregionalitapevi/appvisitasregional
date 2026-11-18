from unittest.mock import Mock,patch
from uuid import uuid4

from django.core.cache.backends.locmem import LocMemCache
from django.test import SimpleTestCase,override_settings

from ColorAdminApp.modules import regional_route_map as maps


@override_settings(GOOGLE_MAPS_API_KEY='offline-test-key')
class RegionalStreetMapTests(SimpleTestCase):
    def setUp(self):
        cache=LocMemCache(str(uuid4()),{})
        patcher=patch.object(maps,'cache',cache);patcher.start();self.addCleanup(patcher.stop)
        self.group={'origin':[-23.54,-46.98],'houses':[
            {'number':i+1,'coords':[-23.54,-46.98+(i+1)*.0001]} for i in range(13)]}

    @patch.object(maps.requests,'get')
    def test_road_map_keeps_every_pin_and_does_not_return_to_origin(self,get):
        directions=Mock();directions.json.return_value={'status':'OK','routes':[{'overview_polyline':{'points':'encoded-path'}}]}
        image=Mock(content=b'fake-image',headers={'content-type':'image/png'})
        get.side_effect=[directions,directions,image]
        result=maps.google_route_map(self.group)
        self.assertEqual(len(result['points']),14)
        self.assertTrue(result['route_available'])
        self.assertEqual(get.call_args_list[1].kwargs['params']['destination'],','.join(map(str,self.group['houses'][-1]['coords'])))
        self.assertNotIn('optimize:',get.call_args_list[0].kwargs['params']['waypoints'])
        self.assertEqual(maps.google_route_map(self.group),result)
        self.assertEqual(get.call_count,3)

    def test_camera_keeps_all_points_inside_map(self):
        coords=[self.group['origin']]+[h['coords'] for h in self.group['houses']]
        center,zoom=maps.camera(coords);cx,cy=maps.mercator(center)
        for point in coords:
            x,y=maps.mercator(point)
            self.assertLess(abs(x-cx)*256*2**zoom,300)
            self.assertLess(abs(y-cy)*256*2**zoom,300)
