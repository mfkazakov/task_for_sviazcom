import main


def test_parse():
    assert main.parse_response('') is None
    assert main.parse_response('abracadabra') is None
    assert main.parse_response('HTTP/1.1 404 ') is None


def test_generate_url():
    assert main.generate_url('Krasnoyarsk') == \
           f'http://api.weatherapi.com/v1/current.json?key=0a6586359d6e4c3084c73940232802&q=Krasnoyarsk&aqi=no'
    assert main.generate_url('kr123asnoyar sk ') == \
           f'http://api.weatherapi.com/v1/current.json?key=0a6586359d6e4c3084c73940232802&q=Krasnoyarsk&aqi=no'

